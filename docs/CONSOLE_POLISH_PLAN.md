# Console polish, round 1

Scope: remove the legacy Streamlit interface, fix the confirmed defects the
operator reproduced against the live console, and take the React console from
"functional" to "usable by a non-technical person without a terminal".

Everything here is code plus local checks. No image builds, no deploys, no
server changes. The operator owns every server-side action.

---

## 1. The problem in one paragraph

Two user interfaces exist. The old Streamlit one is still served on 8501 and
still reachable. The new React console on 8504 works but reads as developer
scaffolding: it says "TEACHINGS" on Home and "Sermons" in the nav, it labels the
same record "READY" on one page and "Processed" on another, it renders an empty
state before the request that fills it has finished, it shows a raw debug string
in a monospace strip across the bottom of New Sermon, and it opens on eleven
Settings tabs with six stacked cards in the first one. A single operator has to
hold a mental map of a product that changes its own vocabulary between screens.

---

## 2. Vocabulary decisions

### The noun

**Sermon.** One word, everywhere in the chrome.

River processes sermons, uploads sermons, and searches for sermons. "Teaching"
is the word the fixture data uses, and it stays there as a placeholder, but no
UI label, heading, button, empty state, or aria-label says "teaching" after this
round. Nav item, page titles, search placeholder, filters, empty states, toast
copy, the New Sermon subtitle, the LibraryDetail not-found copy.

SermonAudio keeps its own capitalisation because that is the vendor's name.

### Status words

The database has exactly four record states. The console had two vocabularies
for them and neither matched the database. One vocabulary now, everywhere:

| Database value | Console label | Why |
|---|---|---|
| `processed` | **Uploaded** | It is on SermonAudio. That is the whole meaning of the value. |
| `draft` | **Draft** | Processed on disk, deliberately not uploaded. |
| `error` | **Failed** | The run broke. |
| `pending` | **Queued** | Created, not processed yet. Nothing exists to play. |

`rendered` is retired as a record status. It was a client-side fiction mapped
from `pending`, and it was labelled "Rendered - not uploaded", which was false: a
pending record has nothing rendered. A record that is rendered but not uploaded
is a `draft` with a render on disk, and that is the state
`sermonActionMatrix.canUploadExisting` already keys off.

Edit-plan status keeps its own vocabulary (`Draft`, `Pending review`,
`Applied - local`, `Processed`, `Superseded`) because a plan is a different
entity from a sermon and the two are compared in `sermonViewMode`.

### Service health words

Three states, and only three: **OK**, **Warning**, **Unknown**.

`Unknown` is new and it is the important one. A check that could not determine
state reports `unknown`, never `warning`. Amber means "pay attention", so it
cannot be spent on "the server did not tell me".

---

## 3. Proposed information architecture

### Primary navigation (unchanged shape, corrected labels)

```
Home            where things stand, and what needs you next
New Sermon      the main path
Library         everything you have
Jobs            work in progress
Settings        nine tabs, no stacked cards
```

Five items, one level, grouped by what River is trying to do rather than by
which backend module serves the request. The logo is not a link today; making it
one is in scope for a later round, not this one.

### Home

Reordered around the question River actually opens the console to answer, which
is "is anything stuck and what do I do about it":

1. **Header.** `New sermon` stays the single primary action.
2. **At a glance.** Four tiles: Sermons, Waiting for you, Active jobs, Services.
3. **Needs you.** Drafts waiting for review and records that failed, each one a
   direct link to its detail page. This is the resume-a-half-finished-sermon
   entry point that did not exist before.
4. **System status.** Six service cards, honest wording, `Not measured` available.
5. **Active jobs**, **Up next**, then **Recent sermons**.

### Settings: ten tabs, none a long scroll

The tab bar already existed. The defect was that the first tab held six stacked
cards. Rebalanced so no tab holds more than two cards, the admin-only ones are
separated from the personal ones, and every documented capability keeps an
addressable home:

| Tab | Cards inside |
|---|---|
| General | General, Processing defaults |
| Audio & Transcription | Audio settings, Transcription settings |
| LLM Providers | LLM connections, routing |
| SermonAudio | Accounts, Single-account fallback, Upload routing |
| Cloud Mounts | Cloud mounts |
| Descriptions & Prompts | Validation, Prompt templates |
| Backup & Restore | Full data backup |
| Appearance & Account | Theme, display name, password reset |
| Users | User administration (admin only) |
| System | Front-door state, the server's own report, log level (admin only) |

The System tab reports what `/api/status` actually says. It used to render three
invented progress bars and a made-up disk figure marked `(mock)`.

Deep links: `?tab=<id>` selects a tab, so any page can send River to the exact
setting that is blocking him. `/settings?tab=sermonaudio` from a refused publish.
The pre-existing `?cloud=connected` link still resolves.

### New Sermon: two required things, then an optional drawer

```
Step 1  Recording       upload / server path / cloud          (required)
Step 2  Details         title, speaker, date                 (required)
                         series, event type, scripture         (optional)
--- Processing options ---                                      (optional, collapsed)
         enhance / transcribe / AI metadata / dry run
         Edit Sermon, approval mode, ending card, fade
Start processing
```

The optional pipeline toggles move behind a disclosure that shows a one-line
summary of what is currently set, so nothing becomes invisible. A live "What
happens next" panel sits above the action button and names the run in plain
words. Field errors appear on blur, not on submit.

### Draft review: one primary action

The approval bar currently shows six equal-weight buttons on desktop
(`Approve - Render-only`, `Approve - Render+upload`, `Upload existing render`,
`Reject with notes`, `Re-detect`, `History`) while mobile already collapses five
of them into a menu. Desktop adopts the mobile pattern:

```
[ Approve & Upload ]  [ More actions v ]
                        Approve render only
                        Upload existing render
                        Reject with notes
                        Re-detect
                        History
```

`Approve & Upload` is the primary because publishing is the point of the
product. Render-only stays one click away for a dry run. The artifact list loses
its per-row previews and collapses to one tidy list of rows, each with a
Download link and a single Play action.

---

## 4. The workflow River actually walks

Plain language, per sermon, no jargon, no terminal.

**1. Get the recording in.** Open **New Sermon**. Step 1 offers three doors:
Upload (drag a file from the computer), Server path (the file is already on the
machine), Cloud file (it lives in Google Drive or wherever). Pick one. The page
tells you immediately whether the choice worked: the file name and size appear,
or a red line says what is wrong.

**2. Say what it is.** Step 2 wants a title, a speaker, and a date. Those three
are required. The speaker box offers names you have used before, so you type
three letters instead of the whole thing. Series, event type, and scripture are
optional and sit in the same panel, marked optional. Anything you leave blank
you can fill in later from the Library.

**3. Choose how it gets processed.** Only if you want to. Processing options are
collapsed by default and summarised in one line: "Clean audio, transcribe, write
the summary, upload at the end." Open it to change any of it. The dry-run switch
stays where it is, in the same panel.

**4. Press Start processing.** The page says what will happen in one sentence,
then the job appears at the top of **Jobs**. A toast tells him the job number
and the page offers a link straight to it. The form clears but the job number
stays, so he cannot lose the handle to the thing he just started.

**5. Watch it run.** Jobs refreshes on its own every five seconds. Each row
shows the state and how long it has been going. The failed tab explains each
failure and offers Retry. This is the one place River currently hits a dead end,
because the bridge is read-only for retry; that is a real gap and it is listed
under gaps below rather than papered over.

**6. Review the draft.** When a run stops for approval, the sermon appears under
**Needs you** on Home and as a Draft in the Library. Open it: the player is at the
top, the proposed cut is drawn on a timeline, and one button says
**Approve & Upload**. Everything else is one click away. If the cut is wrong,
drag the handles or type the times, then approve.

**7. Publish.** Approve queues the render and the upload. The page says it is
queued and points at Jobs.

**8. Confirm it landed.** Back on the sermon, the status chip reads Uploaded and
there is a link to the sermon on SermonAudio. If the upload failed, the status
reads Failed, the error is spelled out, and the action becomes "Try the upload
again" rather than a dead end.

Nothing in that path needs a terminal, a log file, or a page whose only content
is an error.

---

## 5. Confirmed defects

### D1. Home reports false warnings for working services (backend)

`server/api/routers/status.py` builds `SystemStatusManager({})`. An empty dict
means `api_key` and `broadcaster_id` are `None`, so the SermonAudio check fails,
and `_context_tolerant()` rewrites the failure into an amber `warning` whose
message ends `unconfigured in API context`. A healthy install shows two amber
cards and `SERVICES OK 2/4`. The live container has the credentials and sermons
have uploaded.

Fix: resolve the real config through the same path the rest of the app uses
(`ui.config_utils.resolve_config_with_sources`, the call
`server/api/routers/app_config.py` already makes), pass it to the manager, and
keep env-override precedence intact. Delete `_context_tolerant()`: with real
config there is no context to be tolerant of. A check that cannot determine state
returns `unknown`, never `warning`. Every non-OK message names the Settings tab
that fixes it, so "API credentials not configured" becomes "Connect a
SermonAudio account in Settings, then try again."

Regression test: constructing the manager with an empty config must fail the
test, and a test that a resolved config produces `ok`/`unknown` and never a
`warning` carrying an internal phrase.

### D2. New Sermon shows a raw debug string

`web/src/pages/NewSermon.tsx` builds `summaryBits` and renders them joined with
` · ` in a fixed strip along the bottom of the viewport:

```
upload:no file · untitled · no speaker · no date · enhance · transcribe ·
ai meta · live run · no edit · out:processed_sermons
```

That is a developer's debug line. It leaks `out:<path>`, it contradicts the
toggles it summarises, and it is the last thing on the page.

Fix: delete it. Replace with a labelled "What happens next" summary panel in
normal flow, above the action button, built from sentences. A test asserts that
no `·`-joined internal token ever reaches the DOM and that none of `no ai meta`,
`live run`, `out:` appear.

### D3. LibraryDetail shows "No files recorded" while files exist

`SermonCompleted.tsx` renders its empty state whenever `files.length === 0` and
its player empty message whenever `!activeItem?.available`. Neither consults
`media.isLoading`. The detail query resolves before the media query, so for a
second or two on every load the page confidently says there is nothing there.

Fix: three states, everywhere. Pending means skeleton. Loaded and empty means
the honest empty message plus what to do next. Loaded with files means the files.
The empty message must not be reachable while a request is in flight. Test
renders with a pending media query and asserts the empty text is absent.

### D4. Remove the legacy Streamlit interface

Last, and as its own set of commits, so the test baseline stays attributable.

Keep: `ui/config_utils.py`, `ui/database.py`, `ui/job_queue.py`,
`ui/job_executors.py`, `ui/job_labels.py`, `ui/system_status.py`,
`ui/sermonaudio_accounts.py`, `ui/upload_only.py`, `ui/version.py`,
`ui/auto_edit_apply.py` (imported by the tests that cover apply behaviour).

Remove: `streamlit_app.py`, `ui/pages.py`, `ui/shared_navigation.py`,
`ui/ui_state.py`, `ui/auth.py`, `ui/ui_processor.py`, `ui/media_server.py`,
`ui/sermon_manager.py`, `ui/analytics_manager.py`, `ui/sermonaudio_analytics.py`,
`ui/sermonaudio_api.py`, `ui/performance_monitor.py`, `ui/sermon_importer.py`,
`ui/ui_pages/` (ten modules), `ui/components/` (five modules).

`sermon_updater.py` imports `get_event_types` from `ui/sermon_metadata.py`,
which imports streamlit at module scope. That function moves to a streamlit-free
module and the call site follows, so the pipeline never needs streamlit.

`ui/config_utils.py` has six function-local `import streamlit as st` calls that
only feed a progress callback. They go.

Also: the eleven tests that import `ui.ui_pages.*`, the singleton list in
`tests/conftest.py`, `pyproject.toml`, the requirements files, `Dockerfile`,
`docker-compose.yml` (stop publishing 8501), `docker/nginx/nginx.conf`,
`docker/start_production.sh`, and the docs that still describe 8501 as the
front door.

Parity audit before deletion: `docs/SETTINGS_PARITY.md` maps every legacy
control to a console home. Every row must have a live destination. The legacy
SQL Config Manager has no console equivalent and the doc says so; it was already
dropped by decision, so it stays dropped. Nothing else is dropped silently.

---

## 6. Tickets

File ownership is disjoint. No two tickets touch the same file.

| Ticket | Owns | Work |
|---|---|---|
| **T1** | `server/api/routers/status.py`, `ui/system_status.py`, `tests/unit/test_system_status.py` | D1: real config, drop `_context_tolerant`, add `unknown`, actionable wording, regression tests |
| **T2** | `web/src/mock/data.ts`, `web/src/api/hooks.tsx`, `web/src/api/jobs.test.ts`, `web/src/pages/Home.tsx`, `web/src/pages/Library.tsx`, `web/src/components/Shell.tsx`, `web/src/components/ui.tsx` (state vocabulary only), `web/src/index.css`, `web/src/test/harness.tsx`, `web/src/pages/SermonVocabulary.test.tsx` | One noun, one status vocabulary, retire `rendered`, Home "Needs you", drop the live/mock badge |
| **T3** | `web/src/pages/NewSermon.tsx`, `web/src/pages/NewSermon.test.tsx`, `web/src/pages/NewSermonDemo.test.tsx`, `web/src/components/Combobox.tsx` | D2 plus progressive disclosure, inline validation, "What happens next" |
| **T4** | `web/src/components/ui.tsx` (async primitive), `web/src/components/MediaPlayer.tsx`, `web/src/components/MediaPlayer.test.tsx`, `web/src/pages/LibraryDetail.tsx`, `web/src/components/SermonCompleted.tsx`, `web/src/pages/LibraryDetail.completed.test.tsx`, `web/src/pages/Jobs.tsx`, `web/src/pages/Jobs.test.tsx` | D3 plus one loading/empty/error pattern, and no dead-end Retry button |
| **T5** | `web/src/components/SermonReview.tsx`, `web/src/components/SermonReview.test.tsx`, `web/src/pages/LibraryDetail.actions.test.tsx`, `web/src/pages/LibraryDetail.completed.test.tsx` | Approval-bar hierarchy, artifact de-duplication, review loading states |
| **T6** | `web/src/pages/Settings.tsx`, `web/src/pages/Settings.test.tsx` | Ten balanced tabs, `?tab=` deep links, real System report |
| **T7** | `docs/CONSOLE_POLISH_PLAN.md`, `docs/SETTINGS_PARITY.md`, `web/README.md` | Docs follow the code |
| **T8** | everything in the D4 removal list, plus `tests/**`, `pyproject.toml`, `requirements/**`, `Dockerfile`, `docker-compose.yml`, `docker/**`, `docs/DEPLOYMENT.md`, `README.md`, `AGENTS.md` | Streamlit removal, its own commits |

Ownership is disjoint except where two tickets had to touch the same file for
unrelated reasons, and each of those is listed here rather than glossed:

- `web/src/components/ui.tsx` is written by T2 (the state vocabulary: `Meter`,
  the `unknown` service state, `Chip`) and then by T4 (the `AsyncSection`
  primitive). Different regions, applied in that order, in one session.
- `web/src/components/SermonCompleted.tsx` and
  `web/src/pages/LibraryDetail.completed.test.tsx` are written by T4 (the
  loading/empty pattern in the files list) and then by T5 (the file-list layout
  and the row shape). Applied in that order.
- `web/src/test/harness.tsx` is shared test scaffolding rather than product
  code; T2 created it and T6 extended it.

---

## 7. What gets deleted from the legacy UI, in order

1. **Dead or dev-only surface first**, so the removal itself has no surprises:
   the Analytics chat (already removed once; the module is dead), the model
   download manager, the fake Test API Connection button.
2. **Pages the console replaced**: Dashboard, Batch update, Validation page,
   Analytics, Sermon import.
3. **The pages the console genuinely replaced with parity**: Library, Jobs,
   New Sermon, Settings.
4. **The frame**: `streamlit_app.py`, `ui/pages.py`, `ui/shared_navigation.py`,
   `ui/components/`.
5. **Streamlit-only helpers**: `ui_state`, `auth`, `ui_processor`,
   `media_server`, `sermon_manager`, `sermonaudio_analytics`, `sermonaudio_api`,
   `performance_monitor`, `sermon_importer`.
6. **The dependency and the port**: `streamlit` out of `pyproject.toml` and the
   requirements files, 8501 out of the Dockerfile's `EXPOSE`, out of
   `docker-compose.yml`, out of the nginx upstream, out of
   `start_production.sh`.

Each step is a commit. The pipeline and the bridge are verified green between
steps, not only at the end.

---

## 8. Non-goals

- **No server changes.** No image builds, no compose changes on the running
  host, no reverse-proxy edits, no flipping `web_console_ready`. The repo
  changes; the operator runs the cutover.
- **No new backend features.** No job retry endpoint, no resumable uploads, no
  scripture overlay, no per-user cloud OAuth. All logged as roadmap items
  already.
- **No pipeline behaviour change.** The API surface, job queue, and processing
  order are untouched. This round is presentation and truthfulness.
- **No rename of `sermons` in the database.** The wire format keeps its names;
  only the words on screen change.
- **No design-token overhaul.** Colours, type scale, and radius stay. The
  existing tokens pass contrast and tap-target gates.
- **No mobile-specific redesign.** Responsive behaviour is preserved and
  checked, not reimagined.
- **No change to fixture data.** "Sample Teaching N" and "Speaker A" stay as
  placeholders.

---

## 9. Gaps found in the flow, not fixed here

Called out because they are real and River will hit them.

1. **A failed job cannot be retried.** The bridge is read-only for retry, so the
   button explains why instead of working. The workflow says "try again" and the
   app cannot. This needs a `POST /api/jobs/{id}/retry`. Not a UI problem.
2. **The dry-run default is off.** New Sermon defaults to a live run that uploads
   to SermonAudio. For a sole operator that is the wrong default. Flipping it is
   River's call, not mine.
3. **`/api/me/files` is scoped to the user's output directory**, not per sermon.
   When two users share an output directory the boundary leaks. Logged in
   `web/README.md`.
4. **Home has no notion of "stuck".** A record that failed two weeks ago and
   nobody looked is invisible. Needs a last-attempted timestamp on the list.
5. **Two browsers, one console.** No live log tail. Jobs polls at five seconds,
   which is fine for state and useless for watching a render progress.