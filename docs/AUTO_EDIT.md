# Auto-Edit

Auto-edit watches the transcript, asks an LLM to find where the sermon actually starts and where the Q&A begins, then cuts the dead time around them. The edited video ends with a logo card and a fade to black, then the normal pipeline continues (metadata, upload).

## Raw ingest is the primary path

Drop the raw multi-GB `mkv`/`mp4` straight from the recorder into the New Sermon page or the CLI. You do not pre-shrink it in kdenlive first. The keeper transcode step handles the shrink automatically before anything else runs, and it keeps the original on disk so every future re-edit starts from full quality.

Two ways in:

- **Server Path tab (recommended for multi-GB raw files).** Put the file in the raw-ingest folder (Docker host path `.../sermonpilot/raw_ingest`, seen inside the container as `/data/raw_ingest`), then paste the container path into the "Server Path (large files)" tab. The app reads the file from disk directly; nothing goes through the browser.
- **Browser upload.** Works for smaller files. The limit is 30,720 MB (30 GB) by default and can be changed with the `STREAMLIT_SERVER_MAX_UPLOAD_SIZE` environment variable (Docker: set it in `.env`; standalone: same variable or edit `.streamlit/config.toml`). Streaming a 30 GB file through a browser POST is slow and memory-hungry, so prefer the Server Path tab at that size.

### Resumability

Browser uploads are **not resumable**: Streamlit buffers the upload server-side, and an interrupted POST has to start over. For large recordings, use the Server Path tab: copying the file to the ingest folder over SMB or rsync is interruptible and resumable at the transfer layer, and the app then reads it from disk. A resumable in-browser uploader (chunked upload endpoint + JS uploader) is deliberately out of scope for v1.7.0; see the follow-up issue linked from the map.

kdenlive stays in the workflow for rare creative edits only: multi-cam cuts, titles, audio surgery. Everything routine is handled here.

## Requirements

- `ffmpeg` on the PATH (keeper transcode and apply both shell out to it)
- An OpenAI-compatible endpoint for cut detection, configured through two env vars in `.env`:

```bash
OPENCODE_GO_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENCODE_GO_API_KEY=your-key
```

- Hardware encoding is optional. The keeper picks its encoder at runtime: NVENC when an NVIDIA GPU is present, then VAAPI (verified on AMD and Intel), then plain `libx264`.

## Configuration

Add this to `config.yaml`:

```yaml
auto_edit:
  enabled: false
  mode: interactive            # interactive | auto
  auto_confidence_threshold: 0.8   # clamped to <= 0.99
  qa_margin_seconds: 3.0
  min_sermon_seconds: 600
  require_review: true         # legacy: true == interactive when mode absent
  logo_path: ''
  logo_hold: 3.0
  fade_to_black: true
  keeper:
    enabled: true
    crf: 20                    # libx264 -crf / nvenc -cq / vaapi -qp (crf+2)
    nvenc: true                # detect chain: nvenc -> vaapi (Intel+AMD) -> libx264
    delete_original: false
    min_source_gb: 2.0
```

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `false` | Master switch for the whole feature |
| `mode` | `interactive` | `interactive` stops for review, `auto` applies without you |
| `auto_confidence_threshold` | `0.8` | Minimum LLM confidence for auto mode (clamped to 0.99) |
| `qa_margin_seconds` | `3.0` | Padding left around the Q&A boundary |
| `min_sermon_seconds` | `600` | Plans that would leave less than this fail validation and go to review |
| `require_review` | `true` | Legacy flag: `true` behaves as `interactive` when `mode` is absent |
| `logo_path` | `''` | Image shown on the end card; empty disables the card |
| `logo_hold` | `3.0` | Seconds the logo card stays on screen |
| `fade_to_black` | `true` | Fade out at the end of the content |
| `keeper.enabled` | `true` | Shrink large sources before processing |
| `keeper.crf` | `20` | Quality level (see encoder mapping above) |
| `keeper.nvenc` | `true` | Allow the NVENC -> VAAPI -> libx264 detection chain |
| `keeper.delete_original` | `false` | Delete the raw source after a verified transcode and an applied edit |
| `keeper.min_source_gb` | `2.0` | Only transcode sources at or above this size |

Set `logo_path` once and every edit and re-edit picks it up automatically, so the card survives the whole life of the sermon.

### LLM pin for cut detection

Cut detection uses its own provider so it does not inherit your metadata model:

```yaml
llm:
  operations:
    auto_edit:
      provider: "openai"   # any OpenAI-compatible endpoint
      openai:
        api_key: "${OPENCODE_GO_API_KEY}"
        base_url: "${OPENCODE_GO_BASE_URL}"
        model: "deepseek-v4.1-flash"
```

If this pin fails to initialize or errors at call time, detection falls back to the global `llm` primary/fallback chain.

## Pipeline

1. Upload (raw file goes in as-is)
2. Options, including the **Edit Sermon (Auto-Edit)** section on the New Sermon page: enable, approval mode, ending card image, fade to black
3. Audio processing, with the keeper transcode as a pre-step
4. Timestamped transcription
5. LLM cut detection, revision 1 saved to `edit_plans`
6. Review gate
7. `apply_edit` (ffmpeg re-encode with the cut, fades, logo card)
8. Logo card (part of the apply)
9. Metadata
10. Upload

The form's section writes per-run overrides into the job config; with the checkbox off, the feature is skipped for that run regardless of the config default.

### Review gate

| Mode | Behavior |
|------|----------|
| `interactive` | Processing stops at `pending_review`. The sermon is saved as a draft so it shows in the Library, and you finish it from the review panel. |
| `auto` | Applies immediately only when all of these hold: `needs_review` is false, confidence is at or above `auto_confidence_threshold`, and `validate_plan` finds no problems. A `needs_review` plan bypasses the threshold check unconditionally and always goes to review. |

If `apply_edit` itself fails, the plan is flagged for review and the sermon lands in the same pending state rather than dying.

## Reviewing in the Library

Open the sermon in the Library and expand the review panel:

- Badges show the plan status and confidence
- Start and end timestamp inputs at 0.1s resolution, validated live against the plan rules (problems are listed inline)
- The LLM's evidence quote from the transcript
- Approve applies the plan and continues the pipeline. Reject drops it.
- Already auto-applied plans show their applied section here
- **Restore original** undoes an applied edit: the original media is reuploaded and the plan is reverted
- **Re-edit** starts a new revision, always in interactive mode

## Re-edit semantics

Re-edits always re-encode from the retained original (or keeper copy), never from the previous edited output, so quality never compounds. Each revision is a new row in `edit_plans`; older rows stay but are marked superseded.

## Keeper policy

The keeper runs before anything else. Sources under `min_source_gb` pass through untouched. Larger sources are re-encoded at CRF 20, which lands around 20-30% of the original size for multi-GB raw recordings. Audio goes out as AAC at 160k. The output is integrity-checked against the source; a failed check keeps the original and processing continues with it.

`delete_original: true` only deletes the raw file after the transcode passed verification and an edit plan has actually been applied to it.

## CLI flags

```bash
python sermon_updater.py new-sermon service.mkv \
  --auto-edit \
  --auto-edit-mode interactive \
  --speaker "Name" --date 2026-09-06
```

| Flag | Effect |
|------|--------|
| `--auto-edit` | Run cut detection with the review gate |
| `--auto-edit-mode {interactive,auto}` | Override `auto_edit.mode` for this run |
| `--edit-plan-file` | Apply an EditPlan JSON file instead of calling the LLM |

## Jobs

The Jobs page has an Auto Edit job type. A run job carries `auto_edit_enabled`, `auto_edit_mode`, and `edit_plan_file`. When a run stops at `pending_review`, an apply continuation job picks it up afterward with the plan id and the final numbers. If the sermon re-lands in `pending_review`, the continuation job reports failure and leaves the plan approved so you can retry from the Library without losing state.

## Media viewing

Recordings and edited outputs are viewable in the browser without exposing files directly: a localhost sidecar serves media over HTTP range requests, and players use tokenized URLs. The review panel shows short video snippets around the proposed cut points so you can see what would be removed, and the sermon detail page has a full player.

## Docker note

Keeper hardware encoding needs the GPU visible in the container. Uncomment the device block for your backend in `docker-compose.yml` (NVIDIA `deploy.resources` section, AMD `/dev/kfd` + `/dev/dri`), as described in the README's Hardware Acceleration section. Without it, the keeper falls back to `libx264`, which works but is slower.
