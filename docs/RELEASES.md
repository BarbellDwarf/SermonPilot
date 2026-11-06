# Releases

## 1.9.4

Replacing a recording no longer means creating a second SermonAudio entry.

A published teaching now offers **Replace recording** in the overflow menu. The uploaded file is treated as a new source: the pipeline transcribes it, enhances the audio, detects and applies the opening and closing cuts, and uploads the render to the same SermonAudio id. The local row keeps its identity and metadata.

- The API endpoint is `POST /api/sermons/{id}/recording`.
- Only processed sermons with a SermonAudio id can be replaced.
- The previous original moves to `_trash`; the new source becomes the retained original.
- A replacement without an auto-edit result supersedes the old cut plan.
- No new header button or mode switch. One menu item opens one file-picker dialog.

### Verification

- Python unit suite: 842 passed, 6 skipped, one unrelated pre-existing prompts config failure.
- Web tests: 231 passed.
- Production web build passes.

## 1.9.2

Patch release. The review timeline overview start and end handles are circles, matching the detail handles and the mockup. No behavior change.

The dependency-security CI job now scans the fully pinned production lock with `--no-resolve`. OSV's resolver cannot handle the `jsonpointer` 3.8 constraint graph, and the scan found no vulnerabilities.

### Verification

- `npm test`: 230 passed
- `npm run build`: passed
- `osv-scanner scan --lockfile prod-requirements.txt --no-resolve`: no issues

## 1.9.1

Security and toolchain patch. The frontend dependency upgrades close all 17 open Dependabot alerts on the default branch.

- `react-router-dom` 6.30.6 -> 7.18.5
- `vite` 5.4.8 -> 8.3.5
- `vitest` 2.1.9 -> 5.1.0
- `@vitejs/plugin-react` 4.3.2 -> 6.2.1
- Node 22 setup added to CI
- `npm audit` and `npm audit --omit=dev` both report 0 vulnerabilities

No application behavior changes. The review editor, waveform timeline, restore original, and playback fixes from 1.9.0 are unchanged.

### Verification

- 230 web tests pass
- Vite 8 production build passes
- Dependabot open alerts: 0

## 1.9.0

The console review screen is rebuilt around trimming first, with middle cuts when needed.

- Two-strip timeline: a full-sermon overview plus a zoomed detail strip with Fit, 2m, 1m, and 30s zoom.
- Server-generated waveform peaks cached per media file.
- Large trim handles, time labels, park-and-set, and ±1s / ±0.1s nudges.
- Drag across the detail strip to remove a middle section, with each cut shown as a compact row.
- One Transcript / Files / Previews / History tab bar.
- Restore original from a draft review or a completed teaching.
- Review media in Matroska is remuxed to a browser-safe `- Preview.mp4`.
- Media responses send `Cache-Control: no-store`.
- Dry runs keep output local and no longer stage, upload, or trash media in cloud output.
- The legacy Streamlit server is retired; the console runs on port 8504 only.

Full notes: https://github.com/BarbellDwarf/SermonPilot/releases/tag/v1.9.0

## 1.8.0

SermonPilot 1.8.0 moves more of the operator workflow into the browser console. The release brings the recording workflow, review decisions, publishing, account settings, and recovery paths into one place while keeping the processing engine and the legacy interface available.

### New in the console

- **New Sermon** accepts a browser upload, an absolute server path inside the configured input roots, or a file selected from a connected cloud mount. Cloud remotes can be connected and browsed from **Settings**.
- **Review** uses one media player and one timeline. The timeline shows the keep region, the opening and closing cuts, and the optional ending card. Start and end points can be adjusted at 0.1-second resolution, with segment previews before approval.
- **Completed sermons** open in a finished view with publication details, scripture fields, transcript, media, and edit history. A published record can be re-rendered or have its details edited.
- **Jobs** carry readable labels, live status, per-job logs, and cancellation. A failed job is run again from its sermon: approve the cut again on the review page, start the run again from **New Sermon**, or upload the render again. **Upload existing render** publishes an accepted local render without rendering it again.
- The console exposes the review state for a record and keeps actions aligned with that state. A sermon awaiting review cannot be published: the publish path refuses and names the state, so the raw source is never uploaded by accident.

### The processing pipeline

- Cut detection proposes the opening and closing boundaries around the sermon and Q&A. Interactive review saves the sermon as a draft for approval. Automatic application requires a healthy detection result, sufficient confidence, and a valid plan.
- Re-edits create a new plan revision and use the retained full-length source or keeper copy. A previous trimmed render is not used as the next render base. Applying an edit updates the same sermon record.
- When video enhancement is requested, the final render consumes the enhanced audio mux. A failed enhancement or video mux stops the run rather than publishing an unintended artifact.
- Measured audio and video correction carries into the final render when automatic correction is enabled. A manual offset remains authoritative.
- A transcript is required before cut detection starts. An unavailable detection result is shown as a failure for review, with a path to adjust the plan or run detection again.
- Description generation stores usable text or leaves the description empty with a review flag. The console offers a retry, and operator edits remain authoritative over generated review data.

### Reliability and data safety

- A sermon has one deterministic record. Re-runs, re-renders, and refine loops update that record and preserve its history instead of creating a second Library row.
- Media deletion is recoverable. Local files move into a dated trash area with a record of their original and new locations. Cloud objects stay on their remote, or move to a dated trash prefix when a remote change is required.
- The job worker uses a single database lease. A cancelled long-running child process is stopped, partial output is moved to trash, and the queue can move on.
- Startup reconciliation closes jobs left in flight by a container restart. Completed output remains available, while an interrupted job is reported honestly so the work can be queued again from the sermon.
- Media previews and file operations stay within the configured roots and the current user's records.

### Configuration and accounts

- Each user can connect their own SermonAudio account in **Settings**. Uploads use the account belonging to the sermon owner, and a user without an account receives a clear refusal before publishing.
- The seeded or environment-provided single account remains a fallback only while no user-managed account exists. The console shows which credential source will win.
- Settings are stored in the application database and shared by the console and processing engine. Environment variables still take precedence, and the Settings screen names the variable responsible for an override.
- Cloud mounts are stored separately for each user. OAuth connections, browsing, staging, and output writes use that user's remote configuration.
- Saved audio settings reach the enhancer on both new runs and review applies. The console's settings sections and the processing engine use the same configuration values.

### Under the hood

- The console streams media with HTTP range requests, so previews do not require loading an entire recording into memory.
- The API and the legacy interface share the same database, job records, and configuration store.
- The health endpoint and generated API metadata use the application version resolved from the project metadata.
- The former embeddings and retrieval-augmented generation surfaces have been removed. The remaining Settings pages describe the supported provider and processing configuration.

### Upgrade note

Restart the deployment after upgrading. The container entrypoint launches the application process that owns the job worker. The worker currently initializes inside the legacy Streamlit process, and the API bridge submits jobs only. After each restart, open the legacy interface once so the worker claims the lease and queued work runs. Console-submitted jobs wait until then.

Stored `whisper_openrouter` transcription settings migrate to `whisper_openai`. If the old backend was in use, set `WHISPER_OPENAI_API_KEY` and any matching `WHISPER_OPENAI_BASE_URL` or `WHISPER_OPENAI_MODEL` values before the first run.

SermonAudio credentials from the environment are seeded into the settings database on first use, and an exported variable still wins while it is set.

Existing records keep working. Startup migration can fold older duplicate rows into one record. The legacy Streamlit interface remains available on its own port; its retirement is a separate decision.

### Known gaps

- The current edit plan has one start boundary and one end boundary. Additional interior cut segments remain outside the plan model.
- Browser uploads restart from the beginning after an interruption. The server-path route is the practical choice for large recordings.
- Trash recovery is a manual move using the trash record. The console does not provide a restore action yet.

See [Auto-Edit](AUTO_EDIT.md), [Deletion policy](DELETION_POLICY.md), [Settings parity](SETTINGS_PARITY.md), and [Cancellation](CANCELLATION.md) for the detailed operator procedures.
