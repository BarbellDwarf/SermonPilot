# SermonPilot console redesign plan

Status: planning document. No application source changes yet.
Scope: `web/` plus the API fields the UI needs to stop lying.
Basis: nine audits in `/tmp/ui-audit/`, `docs/UI_CORRECTIONS.md`, `web/DESIGN.md`,
`AGENTS.md`, and a read of the current implementation at `d4d2532`.

## 1. Verdict and target outcome

The console looks finished and behaves like a prototype of one workflow. The
visual system survives. The structure does not. Five peer pages each describe
the same teaching with a different word, the one human decision that matters
(approving a render) has no queue and sits below the fold, a failed job cannot
be retried, and Settings carries three competing save primaries.

Target outcome: an operator opens `/`, sees the teachings that need them,
opens one, and finishes it without hunting. One lifecycle label per record on
every surface. One primary action per view. A job is always reachable from its
teaching and back. Settings has one save surface per dirty section. Mobile
approves and monitors; desktop edits and inspects.

The full audit defect list is closed by the end of Phase 6. Phase 0 closes the
three P0s and installs the test gates that would have caught them.

## 2. Goals, non-goals, success measures

**Goals**

1. One lifecycle vocabulary driven by `edit_status`, `status`, `upload_status`
   and the latest plan status.
2. A review queue that is the default screen.
3. One teaching route with one skeleton, editable while work is pending and
   read-mostly once published.
4. A working failure path: retry a job, open the teaching, open the job.
5. One save surface per dirty Settings section, named, secondary.
6. Deterministic tests for hit targets, primaries, validation, tabs, titles,
   lifecycle labels and axe.

**Non-goals**

- Rewriting the backend pipeline, the job worker or the SermonAudio client.
- A second UI implementation for mobile. One route set, different composition.
- Autosave in Settings (backlog, see §10).
- Bulk actions, CSV scope work, transcript search, analytics, keyboard
  shortcuts, account switching.
- Removing Streamlit or other legacy work tracked in `docs/UI_CORRECTIONS.md`.
- Validating live SermonAudio or worker behaviour. Those checks are marked
  manual and are never a phase exit condition.

**Success measures** (all measurable in mock mode except where marked manual)

| Measure | Target |
|---|---|
| Clicks from `/` to a queued approval job | 3 or fewer |
| `approve-primary` position at 390/768/1440 with `scrollY = 0` | inside the viewport |
| Visible accent-filled primaries per view | exactly 1, or 0 where the state has no forward mutation |
| Same record, same lifecycle label on Inbox, Library, workspace | 0 mismatches in a DOM sweep |
| Serious or critical axe findings, 6 routes x 3 viewports x 2 themes | 0 |
| Visible Settings save bars at any scroll position | at most 1, never `primary` |
| Retry on a failed job | creates a linked job (manual live check), shows the new job id in mock |
| Search `Sample 2` | returns Sample Teaching 2 |
| `document.title` | route-specific, teaching title on the workspace |
| `npm test`, `npm run build`, `npm run visual`, `npm run a11y` | pass |

## 3. Target information architecture

### Routes

| Route | Screen | Notes |
|---|---|---|
| `/` | Inbox | Default. Work grouped by next action. |
| `/new` | New teaching | Three steps, one primary. |
| `/teaching/:id` | Teaching | One skeleton. Pending work or published record. |
| `/library` | Library | Archive, search, sort, export. No primary. |
| `/activity` | Activity | Job log and recovery. |
| `/activity/:id` | Activity | Same page, that job expanded. Deep link. |
| `/settings/:section` | Settings | `/settings` redirects to `/settings/preferences`. |
| `*` | Not found | `EmptyState` with a link to Inbox. |
| `/library/:id` | redirect | To `/teaching/:id`, preserving search and hash. |
| `/jobs`, `/jobs/:id` | redirect | To `/activity`, `/activity/:id`. |

`/login` stays inside `AuthGate`; it is not a `Routes` entry today and does not
become one.

### Navigation per breakpoint

| Width | Navigation | Items |
|---|---|---|
| `< 768` | Bottom bar, 56px + safe area | Inbox (review count), Library, New teaching, Activity (one badge), Settings |
| `768-1023` | Left rail 208px | Inbox (count), Library, New teaching, Activity, Settings |
| `>= 1024` | Left rail 224px | Same five items |

One creation entry point per viewport: the rail item on desktop and tablet, the
centre tab on mobile (`aria-label="New teaching"`, visible label `New`). No page
header ever carries a `New teaching` button again. Empty states keep their CTA.

Badges, one channel each: Inbox shows the needs-review count. Activity shows a
danger dot when a job failed since the last visit, otherwise the count of
running plus queued jobs. Never both. No other badge exists.

### Page inventory and what each screen is for

| Screen | Question it answers | Primary |
|---|---|---|
| Inbox | What needs me now? | Row verb: Review, Publish, Upload, Retry, View job |
| New teaching | Start a run | Start processing |
| Teaching | What will publish, and is it right? | Approve & upload, Upload to SermonAudio, Publish draft, Run cut detection, or none |
| Library | What exists? | None; row opens |
| Activity | What ran, what broke, what can I do? | Row verb: Retry, View teaching, Stop job |
| Settings | Change configuration | Section save, secondary, only while dirty |

### Removed, by breakpoint

**Desktop (>= 1024)**

- Home as a summary page: the stat strip, `Pipeline health` section,
  `Active jobs`, `Recent teachings`.
- `New teaching` in the Home, Library and Jobs page headers.
- The `Settings` link under Pipeline health.
- `Rendered` as a label; the separate `ready/processing` Home map.
- Jobs tabs. Activity uses one list with filter chips.
- The dual detail skeleton: `SermonCompleted` as a separate page architecture.
- `Player & plan` heading and its `drag / timeline / cut plan` subtitle.
- The 90px `Preview available in the live console` panel when no media exists.
- The repeated danger-outline `Remove` on every cut row.
- `Save details` as a primary; `Push details` as a label.
- `Check for a plan`; the dead `Retry` button.
- Settings: the 11-section `General` grab-bag, the `System` card inside it, the
  `Prompts` single-item group, and the settings sub-rail at 768.
- `row` copy on the Activity page (`run`, `runs`).

**Tablet (768-1023)**

- All desktop removals, plus the Library table (two-line rows instead), the
  Settings sub-rail (section select until 1024), and the two-column workspace
  (single column with a bottom action bar).

**Mobile (< 768)**

- Timeline editing: jump buttons, zoom row, cut switches, exact times,
  `Restore original`, `Cut this out`.
- The metadata edit form. Details are read-only; the action is `Send back with
  note` or `Approve & upload`.
- The second fixed bar. One sticky action bar above the nav.
- Pipeline health detail and service copy.
- CSV export and any bulk selection.
- The `Output location` disclosure.
- Account fields beyond display name and sign out.

### DESIGN.md corrections this plan requires

`web/DESIGN.md` stays authoritative. These are edits to it, made in the PR that
first needs each one:

| Change | Reason |
|---|---|
| Replace the type-scale table with the Tailwind mapping (`xs 12`, `sm 13`, `base 15`, `lg 17`, `xl 18`, `2xl 24`) and delete the dead `--font-sm/lg/xl/2xl` variables or wire them | Nine sizes render, three below the documented floor |
| Add `--selected` and `--selected-border` and one `selectedClass` used by the rail, settings rail, filter chips and row hover | Light theme selected state measures 1.05:1 |
| Add `shadow-menu` and `shadow-sticky` tokens; `ui.tsx`, `Combobox`, `toast.tsx` and `SaveBar` use them | Three shadows for one role |
| State the six lifecycle labels and their tones in the chip section | Five vocabularies today |
| Add row slot widths: state 104px desktop / 88px mobile, evidence 72px, action 112px, menu 44px; title `min-w-0 flex-1` | Titles and chips move between rows |
| Raise the sheet radius to `rounded-xl`; ban bare `rounded` | Off-scale radii at 17 call sites |
| Forbid an absolute full-row link over interactive controls | Root cause of UI-01 |
| State `info` for running, `accent` only for primary action and focus ring | Accent overload |
| Inputs use 16px minimum at `< 768` | iOS focus zoom |
| Nav vocabulary: Inbox, Library, New teaching, Activity, Settings | Current mix of `Jobs`, `New`, `Home` |

## 4. One lifecycle model

Derived in one function from four inputs: `edit_status`, `status`,
`upload_status`, and the latest `edit_plans.status`. Precedence is first match
wins. The same function feeds Inbox, Library, the workspace header, the nav
count and the tests.

| # | Condition (first match wins) | `OperatorState` | Label | Tone | Primary action | Overflow |
|---|---|---|---|---|---|---|
| 1 | `status = error` or `upload_status = failed` or `edit_status = failed` | `failed` | Failed | danger | `Retry` (retry the last job when its id is known, else `Retry upload`) | Open job, Delete |
| 2 | `edit_status = applied` | `processing` | Processing | info | `View job` | Delete |
| 3 | `edit_status = rendered` | `ready` | Ready to publish | ok | `Upload to SermonAudio` | Re-render, Edit details, Delete |
| 4 | plan status `pending_review` or `edit_status = pending_review` | `review` | Needs review | warn | Row: `Review`. Workspace: `Approve & upload` | Render only, Reject with notes, Re-detect, Delete |
| 5 | `edit_status = uploaded` or `status = processed` | `published` | Published | ok | none | Update SermonAudio details (inside Details, dirty only), Replace recording, Delete |
| 6 | `status = draft` or `edit_status = draft` or no other match | `draft` | Draft | neutral | A render exists: `Publish draft`. Otherwise: `Run cut detection` | Edit details, Delete |

Rules that fall out of the table:

- The chip renders the label only. Revision, confidence, kept duration and QA
  live in the status line, never inside the chip.
- `published` has no primary. "Update SermonAudio details" is a secondary inside
  the Details tab, disabled while clean. This satisfies one-primary without
  inventing a fake action.
- Approving moves the record to `processing` when the apply route returns a job
  id. The primary becomes `View job`, the approve control is disabled until the
  job ends, and the page invalidates plan, sermon and jobs. `revisionsTotal` is
  not mutated.
- `draft` with no render gets detection, not a refetch. `Check for a plan` is
  deleted.
- A failed record shows the last job's first error line in the status line, plus
  `Open job`.
- Unknown combinations fall to `draft` and render the raw `status` in a `title`
  attribute. They never fall through to a success tone.

### Two backend facts that decide whether this can work

1. `edit_status` exists in SQLite and is selected by `get_all_sermons`
   (`ui/database.py:1945`) but `_row_to_list_item` (`server/api/routers/sermons.py:115`)
   drops it, and `SermonListItem` has no field for it.
2. `pending_review` is in `SERMON_LIFECYCLE_STATUSES` but nothing writes it to
   `sermons.edit_status`. A pipeline run that parks a plan stops at
   `ui/job_executors.py:1211` and `:1383` without setting `edit_status`. So
   exposing `edit_status` alone still cannot answer "what needs review".
   The plan therefore exposes the latest plan status too, and adds the two
   one-line writes.

## 5. Page specifications

Every page: `PageHeader` with an `h1`, 24px between page sections (`gap-6`),
16px inside a section, `max-w-[78rem]` main, no horizontal overflow at 390,
768, 1024, 1440.

### 5.1 Inbox `/`

Replaces Home. Sections are lifecycle states that need a person, in this order:
`Needs review`, `Ready to publish`, `Processing`, `Failed`, `Drafts`. A section
with zero rows is not rendered. A footer line carries service health and this
week's publish count.

| | Layout |
|---|---|
| 1440 | Single column of sections, each a card with a heading, count and `TeachingRow` rows. Footer one line: `Services 3/4 · Published this week 4 · Open library`. |
| 768 | Same, rail persists, rows keep the state slot but drop the evidence column. |
| 390 | Same sections as cards. Each row becomes a 112px card: state chip, title, `speaker · date · duration`, one full-width secondary verb. |

- Primary: none at page level. Each row carries its own verb, which is the only
  accent-filled control in view. At most one row action is accent at a time;
  rows that are not the top of their section use secondary.
- Empty: `Nothing needs you.` plus `Next run` (if the API exposes it) and one
  `New teaching` secondary. Empty is a real screen, not a blank page.
- Loading: section skeletons (`SkeletonList variant="row"`), no zero counts.
- Error: `QueryError` with retry, plus the last-known sections if cached.
- Deferred on mobile: evidence column (confidence, elapsed), the footer detail
  beyond `Services 3/4`.

Data: one `GET /api/sermons?limit=50` with counts, or the mock equivalent.

### 5.2 New teaching `/new`

One page, three numbered sections: Source, Details, Pipeline. `Run setup`
(output location, event type default, dry run) moves out of the middle of the
form into the third section, with the dry-run toggle visible, not buried in
`Advanced`.

| | Layout |
|---|---|
| 1440 | Two columns: form `1fr`, sticky run summary `20rem` on the right holding `Start processing` and `Still needed: ...`. |
| 768 | One column; summary becomes a full-width sticky bar at the bottom. |
| 390 | One column; one 56px bar above the nav, one line of summary plus the primary. |

- Primary: `Start processing`, always the only accent control. `Choose file` is
  secondary.
- Source: one control. The dropzone is not a `role="button"` wrapper around a
  button. Keep a real `input[type=file]` out of the tab order and one visible
  secondary button as the click target. No `role="tabpanel"` on the panels.
- Output location: `For this run` plus an explicit `Save as my default`.
  Changing the per-run field never writes the default endpoint.
- Readiness: one line above the primary sourced from the health data
  (`SermonAudio account: connected`, `LLM: available`). Missing account disables
  start with the reason in `aria-describedby`.
- Validation: no `role="alert"` and no `aria-invalid` on first paint. Errors
  appear on blur or submit attempt, linked with `aria-describedby`; the first
  invalid field receives focus. The summary line is descriptive text
  (`Still needed: title, speaker, date`) with `role="status"`, not `alert`.
- Empty: the form itself. Loading: none. Error: inline per field plus a page
  level `QueryError` for facets and branding.
- Deferred on mobile: the sticky run summary's full bit list; the `Save as my
  default` control stays.

### 5.3 Teaching workspace `/teaching/:id`

One skeleton, two modes. Mode comes from the lifecycle state, not from a
separate component page. Published records open the record view with the same
header, tabs and action bar.

```
header:  back (Inbox) | title | speaker · date | status chip | one primary | menu
body:    player + timeline + plan   (work mode)
         record summary + publication (published mode)
tabs:    Details, Transcript, Files, History   (same order both modes)
bar:     sticky action bar at the bottom of the content column
```

| | Layout |
|---|---|
| 1440 | `grid-cols-[minmax(0,1fr)_20rem]`. Left: player, timeline, cut plan, tabs. Right: decision rail with status line, kept duration, cut count, QA, primary and `More actions`. Rail is `sticky top-20`. |
| 768 | Single column. The decision rail moves into the sticky bottom bar: status chip, kept duration, primary, `More actions`. Details stays a tab. |
| 390 | Single column: header, one-line status (`2 cuts · kept 41m 44s · 87% · no problems`, tap opens a status sheet), player, read-only cut list, tabs as accordion rows, sticky bar with `Approve & upload` and `Send back with note`. |

- Primary by state: see §4. The approve control is the only accent control on
  the page.
- Approving: the bar is replaced by `Queued as job 1042 · Rendering, then upload`
  with a link to `/activity/1042`. Approve is disabled while a job is active.
- Details: editable on desktop, first tab, all fields open (title and speaker
  are not hidden behind a disclosure). `Save details` is secondary. On mobile
  the tab is read-only with `Send back with note`.
- Cut plan: one switch per row, secondary actions in the row menu
  (`Preview join`, `Delete cut`, `Restore start`, `Restore end`). Zero-length
  rows are not rendered. The summary separates boundary trims from interior
  cuts.
- Timeline and cut list share one selected-cut state. Selecting a row highlights
  the timeline region; selecting a region highlights the row.
- Loading: header skeleton plus body skeleton. Not found: `h1` plus `EmptyState`
  plus `Back to Inbox`. Error: `h1` plus `QueryError`.
- Deferred on mobile: editable timeline, editable cut rows, exact times, restore
  original, metadata form.
- Manual-only: live playback, waveform, transcript fetch, approve against the
  real pipeline.

### 5.4 Library `/library`

| | Layout |
|---|---|
| 1440 | One row: search `1fr`, lifecycle filter, sort, overflow. Rows 64px: title and meta `1fr`, series 14%, date 96px mono, duration 72px mono, state 104px fixed, menu 44px. |
| 768 | Search full width; filter and sort share a second row; series drops to the meta line. |
| 390 | Search, then `Filters` secondary opening a sheet with lifecycle and sort. Rows: title, state chip right, meta line with duration. |

- Primary: none. Zero accent controls on this page.
- Row: title is the link. No absolute overlay link. The menu keeps `Preview`
  only in demo, and `Open` stays implicit through the title. Delete lives on the
  workspace.
- State filter options and counts: `All`, `Needs review`, `Ready to publish`,
  `Processing`, `Failed`, `Drafts`, `Published`. No `Rendered`.
- Search is tokenized server-side: every whitespace token must match title,
  speaker or series. Sort keys: date, title, speaker, series, duration, with
  direction. `q`, `state`, `sort`, `dir`, `page` live in the URL, restored on
  back navigation with scroll.
- Count line: `1-50 of 128` from the server total.
- Empty: no records at all (`No teachings yet`, one secondary CTA) versus no
  matches (`No teachings match "sample 2"`, `Clear filters`).
- Deferred on mobile: series column, CSV export, bulk selection.

### 5.5 Activity `/activity`

Replaces Jobs. One list, filters instead of tabs, running first then failed then
finished by default.

| | Layout |
|---|---|
| 1440 | Filter chips (`All 5`, `Running 1`, `Queued 1`, `Failed 1`, `Finished 2`), 56px rows, expanded detail inline with actions at the top of the detail. |
| 768 | Same, timestamp column shrinks, title full width on the second line. |
| 390 | Chips scroll horizontally, 84px rows with the timestamp demoted, detail opens inline with actions first so they are not under the nav. |

- Row: state chip, `teaching · action`, elapsed or duration, created, progress
  for running, first error line for failed, chevron. The teaching name links to
  `/teaching/:id`. The job id copies with one click.
- Failed row: primary `Retry` at row level, plus `View teaching`. Retry posts to
  the retry route and opens the new job. No `Cancel` on a failed job.
- Running row: `Stop job`, confirm copy states the undo window and the toast
  matches.
- Expanded: log on one axis (`overflow-y-auto`, `break-words`), parameters, job
  id, and the teaching link. `?job=` state so `/activity/1042` opens expanded.
- Empty per filter: names what the filter means and offers the next filter.
- Loading: row skeletons. Error: `QueryError` with retry, list keeps polling.
- Deferred on mobile: the parameters table (behind a disclosure), log download.

### 5.6 Settings `/settings/:section`

| | Layout |
|---|---|
| 1440 | App rail plus one settings rail (240px) and one form column. Sections: Processing (Audio, Transcription, Validation, Resources), Connections (LLM, SermonAudio, Cloud), Automation (Prompt templates), System (Storage, Advanced, Backup & restore), Access (Users, admin only), Preferences (Appearance, Account). |
| 768 | Section select, no second rail, one form column at least 420px. |
| 390 | Section select, one column, one save bar above the nav when dirty. |

- Primary: the section save is secondary. There is no page primary.
- Save model: one `SaveBar` per dirty section, label `Save audio settings`,
  rendered only while dirty, `Saved.` clears after 3s. At most one bar visible at
  any scroll position, because each section renders one bar and the page shows
  one section.
- Unsaved guard on section change and on leaving.
- Theme: saving applies `html.light` / `html.dark` immediately and at boot. The
  copy names the control that exists (the account menu toggle) or the toggle
  moves to the header. One source of truth.
- Output settings live only here. `/new` reads the resolved default.
- No loading flash: section skeletons. Error: inline `role="alert"` next to the
  field plus the bar's error text.
- Deferred on mobile: nothing removed except the second rail; admin sections
  stay reachable from the select.

## 6. Shared component contracts

All of these live in `web/src/components/ui.tsx` unless noted. One file, one
owner per phase, so parallel agents do not collide.

| Component | Contract | Acceptance rule |
|---|---|---|
| `Menu` | Panel rendered with `createPortal` to `document.body`, `position: fixed` from the trigger rect, `max-h-[min(60vh,20rem)] overflow-y-auto`, flip above when it does not fit below, shift inside the viewport, close on `focusout` when focus leaves trigger and panel, Escape returns focus, arrows and Home/End move the active item, `shadow-menu`. Props unchanged. | `elementFromPoint` at every item centre returns that item at 1440 and at 390x568 on the last row. Panel `bottom <= innerHeight` and `top >= 0`. Clicking `Preview` keeps the URL and `h1` on the same teaching. No row link may cover an open control. |
| `Dialog` | New primitive on native `<dialog>` with `useId` for title and description, `aria-labelledby`/`aria-describedby`, `intent: "default" \| "destructive"`, `busy`, sticky header and footer, scrollable body, focus sentinels, body scroll lock, focus returned to the opener, backdrop detected by pointer coordinates (not `target === dialog`). Destructive intent disables Escape and backdrop dismissal. `ConfirmDialog` becomes a thin wrapper. | Each instance has unique ids. A click 6px inside the card does not close it. Tab stays inside across 20 presses. Escape and close return focus to the opener. |
| `Sheet` | `Dialog` with `placement="sheet"`: bottom, `90dvh`, `rounded-t-xl`, safe-area bottom padding, scrim, title. | At 390x844 the sheet traps focus, Escape closes, focus returns, and no part of it sits under the bottom nav. |
| `Tabs` | New primitive: `items: {id,label,panel}[]`, `value`, `onChange`, `label`, optional `param`. Roving tabindex, Arrow/Home/End, focus follows selection, all panels mounted with `hidden`, `aria-controls` resolves for every tab, optional `?tab=` sync. | Exactly one tab stop per tablist. `?tab=files` restores the Files panel on load. Used by the workspace only; Activity uses filters. |
| Save model | Explicit save, not autosave. `SaveBar` is secondary, named, rendered only while dirty, resets `Saved.` after 3s. One visible per viewport. | At every scroll position at 390 and 1440, at most one visible save bar, never `bg-accent`, label contains the section name, clean sections render no bar. |
| Validation | `Field` gains `error`, `invalid`, `required`, wiring `aria-invalid` and `aria-describedby` (hint id plus error id). `useFieldState` returns `{touched, markTouched, showError}`. Errors only after touch or submit. First invalid field is focused. | Fresh `/new` has zero `role="alert"` and zero `aria-invalid`. Blur on an empty required field shows its message and links it. |
| Toast | Queue instead of slicing at three. Always render dismiss alongside an action. `error` defaults to `duration: 0` with explicit dismiss. Host gets `role="region"` (or drops the label). Offset from `--chrome-bottom`, not a constant. | Four rapid pushes keep all four. The undo toast has `Undo` and `Dismiss`. Focus on a toast prevents auto-dismiss. Toast never overlaps a sticky bar (`toastRect.bottom <= barRect.top - 8`). |
| Status chip | `<StatusChip state={OperatorState}>`; label and tone from `utils/lifecycle.ts`. Accepts no free text. | A DOM sweep finds no label outside the six. The same id shows the same label on Inbox, Library and the workspace. |
| Row slots | One `TeachingRow` used by Inbox and Library. Slots: state 104px desktop / 88px mobile, title `min-w-0 flex-1` plus meta line, evidence 72px mono, action 112px, menu 44px. Status never precedes the title. Title is the link. | A 90-character title does not move the chip or the menu. Chip right edge is identical on every row. At 390 the title column is at least half the row. |
| Chrome budget | `--chrome-bottom: calc(56px + env(safe-area-inset-bottom))`, `--chrome-bar: 56px`. Shell padding, sticky bars and toast offset read them. | No two fixed layers intersect. Header plus one bar plus nav at 320x568 is at most 32% of the viewport. |

## 7. Data and API work

Keep the API shape otherwise. These changes are the minimum that lets the UI
tell the truth.

| Change | File | Detail |
|---|---|---|
| Expose the lifecycle on list items | `server/api/schemas.py`, `server/api/routers/sermons.py` | `SermonListItem` and `SermonDetailOut` gain `edit_status: str \| None`, `upload_status: str \| None`, `plan_status: str \| None`. `_row_to_list_item` copies them. |
| Read the latest plan status without a second query | `ui/database.py` | Add the latest `edit_plans.status` per sermon to the `get_all_sermons` select as `latest_plan_status` (correlated subquery on max revision). Extra dict key only, no consumer breaks. |
| Write `pending_review` when a plan parks | `ui/job_executors.py` | Set `edit_status = "pending_review"` at the two park points (`:1211`, `:1383`), next to the existing log line. |
| Counts by lifecycle | `server/api/schemas.py`, `server/api/routers/sermons.py` | `SermonListOut` gains `counts: dict[str, int]`. `list_sermons` computes counts over all scoped rows in one pass. |
| `state` filter and real paging | `server/api/routers/sermons.py`, `web/src/api/client.ts` | `state: str = ""`, `dir: str = "desc"`, `limit`, `offset`. Tokenized search (`needle.split()`, every token must match title, speaker or series). Sort keys `date`, `title`, `speaker`, `series`, `duration` with direction. `total` is the filtered count. |
| Job retry route | `server/api/routers/writes.py`, `web/src/api/client.ts` | `POST /api/jobs/{job_id}/retry` calls `job_queue.retry_job` (`ui/job_queue.py:1043`), returns `{job_id, status}`, 409 when the queue is busy, ownership checked like cancel. Manual live validation only. |
| Publish a dry-run draft | `server/api/routers/writes.py`, `web/src/api/client.ts` | `POST /api/sermons/{id}/publish-draft` wraps `publish_dry_run_sermon` (`sermon_updater.py:4652`) with an ownership check, returns `{job_id, status}`. Manual live validation only. |
| Job list total and per-state fetch | `server/api/routers/jobs.py` | Return a real `total` (not `len(items)` after the limit), accept `offset`, and include `interrupted` in the failed filter. |
| Client types | `web/src/api/client.ts` | `ApiSermonListItem` fields, `ApiSermonList.counts`, `api.sermons` params, `writeApi.retryJob`, `writeApi.publishDraft`. |
| Lifecycle helper | new `web/src/utils/lifecycle.ts` | `OperatorState`, `operatorState()`, `STATE_LABEL`, `STATE_TONE`, `PRIMARY_ACTION`, `needsAttention`. Single source in TS; the server's `state` filter is tested against the same fixture table. |
| Remove the Home data path | `web/src/api/hooks.tsx` | Delete `useHomeData`, `toRecentSermon`, `SERMON_STATUS_MAP` once Inbox lands. |
| Shared sermon query | `web/src/api/hooks.tsx` | `useSermonsQuery(params)` with `placeholderData: keepPreviousData`, key `["sermons", {params}]`, consumed by Inbox and Library. Keep the mock branch inside the hook, not in pages. |
| Fixtures | `web/src/mock/data.ts` | One record per lifecycle state, agreeing across every surface; a draft with a render; a failed job linked to its teaching; a long title, empty series, non-Latin title; `plan_status` on each record. Delete the `ready/processing/draft/failed` Home enum and `recentSermons`. |

Backend tests: `tests/unit/test_sermons_api.py` (list fields, counts, state
filter, tokenized search, paging), `tests/unit/test_jobs_api.py` (total, offset,
retry route), plus a fixture table test asserting the Python `state` filter
matches the TS table in `web/src/utils/lifecycle.test.ts`.

## 8. Phased delivery

Each phase is one or more PRs, independently shippable, with the app usable at
the end. Branches come off the active release branch (`release/v1.9.4` today)
and PR into it. No direct commits to `main` or `master`. Every phase ends with
`npm test`, `npm run build`, `npm run visual`, a `visual-qa` agent run over the
phase's routes, and `npm run a11y` once Phase 0 adds it.

File ownership is column-scoped so agents can work in parallel. Two agents never
edit the same file in one batch.

### Phase 0: Stabilise the current UI

Objective: close the three P0s and install deterministic gates, without touching
routes or the data model.

File ownership: Track A `web/src/components/ui.tsx`, `web/src/components/toast.tsx`;
Track B `web/src/components/SermonReview.tsx`; Track C `web/src/pages/NewSermon.tsx`;
Track D `web/playwright.config.ts`, `web/package.json`, `web/tests/visual/**`.

Tasks

1. `Menu` portal, viewport clamp and flip, close on focusout. UI-01.
2. Review sticky action bar at the bottom of the content column, above the
   mobile nav; `Approve & upload` the only primary; `Save details` secondary;
   remove the duplicate bottom approve block; compress the status strip to one
   line plus revision and confidence. UI-02, W-11.
3. New teaching: remove `role="button"` from the dropzone and the nested button,
   make `Choose file` secondary, gate `role="alert"` and `aria-invalid` on touch,
   add inline errors for title, speaker and date, drop `role="tabpanel"` from
   the source panels, `tabIndex={-1}` on the file input. UI-03, UI-04, UI-05.
4. `Skeleton` loses `aria-label`; `ToastHost` loses the prohibited label or gains
   a role. UI-07.
5. Touch targets: 44px for timeline jump and zoom, info tabs, `Exact times`,
   `Output location` summary. UI-08.
6. Per-route `document.title` and focus the `h1` on route change. UI-10.
7. Skip the demo waveform request when `!isLive`. UI-11.
8. Fix `label-content-name-mismatch` (logo link, account trigger, Home row
   links, dropzone) and the dark accent-on-`accent/15` contrast.
9. Add `@axe-core/playwright` and `web/tests/visual/a11y.spec.ts`; add
   `web/tests/visual/interaction/` with the UI-01, UI-02 and UI-03 specs.

Tests: the named specs in §9 for UI-01, UI-02, UI-03, touch targets, axe.

Acceptance: UI-01, UI-02, UI-03, UI-04, UI-05, UI-07, UI-08, UI-10, UI-11 pass;
axe has zero serious or critical findings on the six current routes at three
viewports and two themes; `approve-primary` is inside the viewport at 390x844,
768x1024 and 1440x900; exactly one accent primary is visible on `/new` and
`/library/s-01`.

Visual QA gate: full matrix on the six current routes. Rollback risk: medium.
`ui.tsx` is used by every screen; a `Menu` regression breaks the account menu
and every row action. Mitigation: unit tests for the primitive, the interaction
spec, and no behaviour change to props.

### Phase 1: Expose the lifecycle

Objective: make the queue computable before any screen changes.

File ownership: Track H `server/api/**`, `ui/database.py`, `ui/job_executors.py`,
`web/src/api/client.ts`, `web/src/api/hooks.tsx`; Track I `web/src/utils/lifecycle.ts`,
`web/src/utils/lifecycle.test.ts`, `web/src/mock/data.ts`, backend tests.

Tasks: the data rows in §7 except the two new write routes, which land in Phase 4
and Phase 3 respectively. Add `operatorState` and the fixture table. Rewrite the
mock data so every surface agrees.

Tests: `lifecycle.test.ts` table over every input combination; Python
`test_sermons_api.py` for fields, counts, state filter, search, paging; mock data
consistency test asserting one label per id.

Acceptance: `GET /api/sermons` returns `edit_status`, `upload_status`,
`plan_status` and `counts`; `state=needs_review` returns only parked plans; a
parked plan writes `edit_status = pending_review` (unit test with a fake repo).
No UI change yet.

Visual QA gate: not required, no visual change. Run the unit and API suites.
Rollback risk: low. Additive fields and one extra dict key. The only risk is the
`get_all_sermons` query shape; guard with the existing repository tests.

### Phase 2: Shell, routes and Inbox

Objective: the default screen becomes the queue; the nav vocabulary becomes one
word per destination.

File ownership: Track B `web/src/App.tsx`, `web/src/components/Shell.tsx`,
`web/src/routes.ts`, `web/src/utils/pageTitle.ts`; Track C new
`web/src/pages/Inbox.tsx`, new `web/src/components/TeachingRow.tsx`, new
`web/src/components/StatusChip.tsx`, `web/src/pages/Home.tsx` (delete); Track G
`web/src/pages/Jobs.tsx` renamed to `web/src/pages/Activity.tsx` and mounted at
`/activity`; Track I route and lifecycle specs. `api/hooks.tsx` stays with
Track H.

Tasks

1. Migrate `BrowserRouter` to `createBrowserRouter` with lazy routes and a
   catch-all. This enables `useBlocker` and code splitting.
2. Route table with titles and redirects from §3. Update Shell items and badges.
3. Build `Inbox`, `TeachingRow`, `StatusChip` on the Phase 1 fields and the mock
   fixture set.
4. Delete Home and `useHomeData`.
5. Rename the Jobs page to Activity and mount it at `/activity` with the new nav
   label. Keep the current tab behaviour until Phase 4.
6. Add `useUnsavedChanges` (router blocker plus `beforeunload`); wire it in
   Phase 4.
7. Empty, loading and error states for Inbox.

Tests: `lifecycle-labels.spec.ts` (same id, same label across Inbox and Library),
`route-title-focus.spec.ts`, `inbox.spec.ts` (every state renders the right
verb; needs-review count equals the filtered list), responsive overflow for `/`.

Acceptance: `/` shows every non-empty lifecycle section with one verb per row;
the nav count matches `counts.needs_review`; `New teaching` appears once per
viewport; no page header CTA. `/jobs` redirects to `/activity`, and Phase 2
ships a working Activity page by moving the existing Jobs list and job detail
behind the new route and nav label. Phase 4 then adds filters, retry and the
deep link; the route never 404s in between.

Visual QA gate: `/`, `/library`, `/new`, `/settings` at 390, 768, 1440 in both
themes. Rollback risk: medium. Route churn breaks bookmarks and tests; the
redirects cover bookmarks. The data-router migration touches `AuthGate` and
`Shell`; keep the same provider order.

### Phase 3: Teaching workspace

Objective: one route and one skeleton for a teaching, with the primary always
visible and one accent control.

File ownership: Track D `web/src/pages/Teaching.tsx` (from `LibraryDetail.tsx`),
`web/src/components/SermonReview.tsx`, `web/src/components/SermonCompleted.tsx`,
`web/src/components/Timeline.tsx`, `web/src/components/MediaPlayer.tsx`, new
`web/src/components/review/*` extracted units, `web/src/components/sermonActions.ts`;
Track H `api/client.ts` for `publishDraft`; Track I workspace specs.

Tasks

1. Extract `useCutEditor`, `DetailsForm`, `ReviewPlayer`, `PlanSummary` from
   `SermonReview.tsx`. Key the cut editor on `planKey` and delete the four reset
   effects. Target: layout under 300 lines.
2. One skeleton: header, body, decision rail, tabs. Published mode uses the same
   header and tabs, with publication rows in the Details tab.
3. Sticky action bar at every width. Primary per §4. `More actions` holds render
   only, reject with notes, re-detect, history, replace recording, delete.
4. Details tab: all fields open, title and speaker included, `Save details`
   secondary, mobile read-only.
5. Cut plan rows: one switch, secondary actions in the row menu, hide zero-length
   rows, separate boundary trims from interior cuts in the summary, share the
   selected cut with the timeline.
6. Post-approve state: job id, link to `/activity/:id`, approve disabled while
   the job runs, invalidate plan, sermon and jobs.
7. Draft primary: `Publish draft` calling the new route, `Run cut detection`
   when no render exists.
8. Delete the dead preview panel and the `Player & plan` heading.
9. Mobile: read-only plan, accordion tabs, `Send back with note`.

Tests: `ui02-primary.spec.ts` (viewport and single primary at three widths),
`workspace-details.spec.ts` (sheet is a dialog, focus trap, Escape), `workspace-
approve.spec.ts` (primary changes, job link appears, second approve blocked),
`workspace-mobile.spec.ts` (no timeline controls at 390), `tabs.spec.ts`,
`lifecycle-labels.spec.ts` extended to the workspace.

Acceptance: `approve-primary` visible at `scrollY = 0` at 390/768/1440; exactly
one accent primary; every lifecycle state has a non-zero primary except
`published`; draft with no plan is not a dead end; dialog semantics on mobile.

Visual QA gate: `/teaching/s-01`, `/teaching/s-02`, `/teaching/s-03`,
`/teaching/s-04` and a no-plan record at three viewports and two themes. Update
snapshots in this PR only. Rollback risk: high. This is the largest change and the
first that invalidates detail snapshots. Land the extractions as separate
commits inside the PR so a regression can be bisected. Manual-only: playback,
waveform, transcript, real approve.

### Phase 4: Activity and recovery

Objective: failures have a working path.

File ownership: Track G `web/src/pages/Activity.tsx`, `web/src/pages/jobRow.ts`;
Track H `server/api/routers/writes.py` retry route, `routers/jobs.py` total and
offset, `web/src/api/client.ts`; Track I activity specs.

Tasks

1. Replace tabs with filter chips and URL state (`?state=`, `?job=`).
2. Failed row: `Retry` primary at row level, `View teaching` link, no `Cancel`.
   Running row: `Stop job` with matching confirm and toast copy.
3. Teaching link from `parameters.sermon_id` when it resolves.
4. `/activity/:id` opens the row expanded.
5. Retry route, 409 handling, new job becomes the active row, toast carries the
   new id.
6. Poll the open job detail while running; log on one axis; actions at the top of
   the detail.
7. Replace `run` and `Sermon processing` in copy. Job type chips read
   `Processing`, `Metadata`, `Transcription`.

Tests: `activity-retry.spec.ts` (one POST, new row, teaching link resolves,
`/activity/job-1037` opens expanded), `activity-tabs.spec.ts` becomes
`activity-filters.spec.ts`, jobs API tests.

Acceptance: a failed job can be retried and linked; `interrupted` appears in a
filter; the total is honest beyond 100; no `Cancel` on failed.

Visual QA gate: `/activity` with the failed row expanded at three viewports.
Rollback risk: medium. Retry is new backend behaviour and is manually validated
live; in mock it is a queued toast plus a new row.

### Phase 5: Intake and Settings

Objective: remove the two remaining multi-primary surfaces.

File ownership: Track C `web/src/pages/NewSermon.tsx`; Track F
`web/src/pages/Settings.tsx`, `web/src/components/*Settings.tsx`,
`web/src/api/useConfigSection.ts`, `web/src/api/useUserSettings.ts`; Track I
intake and settings specs.

Tasks

1. New teaching: three sections, run summary rail or bar, one primary, readiness
   row, `For this run` versus `Save as my default`, visible dry run, event type
   default shown, source format list derived from `accept`, guarded navigation.
2. Settings: split `General` into Preferences (Appearance, Account) and Access
   (Users). Remove the `System` card, fold `Prompt templates` into Automation,
   move the section rail to `>= 1024`.
3. One save bar per dirty section, secondary, named, only while dirty, `Saved.`
   clears. Fix the theme preference so it applies and persists.
4. Port `useConfigSection` and `useUserSettings` to react-query with optimistic
   save and one invalidation path.

Tests: `ui03-validation.spec.ts` (no alerts on load, blur errors, focus first
invalid), `settings-save.spec.ts` (one visible bar, named, secondary, clean
sections have none), `settings-theme.spec.ts` (light applies and survives
reload), `intake-guard.spec.ts`.

Acceptance: one accent primary on `/new`; at most one save bar at any scroll
position; no section save uses primary; no `Saved.` on a clean section.

Visual QA gate: `/new`, `/settings/preferences`, `/settings/audio` at 390, 768,
1440 in both themes, plus a dirty-section state at 390. Rollback risk: medium.
Settings split changes URLs; `/settings?section=general` redirects to
`/settings/preferences`.

### Phase 6: Tablet and mobile composition, cleanup

Objective: apply the breakpoint split and delete what is now unused.

File ownership: Track A `ui.tsx` (Sheet, Tabs), `index.css`, `tailwind.config.js`,
`web/index.html`; Track C `pages/Library.tsx` (two-line rows, filter sheet);
Track D mobile read-only workspace refinements; Track I full matrix.

Tasks

1. Library: two-line rows below 1024, filter sheet below 640, no series column,
   URL state, tokenized server search with `keepPreviousData`.
2. Workspace: single column below 1024, remove mobile editing, accordion tabs.
3. Platform baseline: `viewport-fit=cover`, `theme-color`, 16px inputs below
   768, `touch-action: manipulation`, hover rules gated on
   `@media (hover: hover)`, `90dvh` sheets, `overscroll-behavior`.
4. Type scale, selected surface token, shadow tokens, radii, `Meter` height.
5. Delete unused components (`SermonCompleted` if fully merged, Home mocks,
   `SermonStatus`), stale light screenshots, and the old `/jobs` code.

Tests: full responsive suite at 320, 390, 768, 1024, 1440; touch-target sweep at
390; axe full matrix; visual snapshots for the final route set.

Acceptance: no horizontal overflow; every control at least 44x44; one visible
sticky layer per viewport; no `Rendered`, `Push details`, `run`, `Sermon
processing` in user-facing copy; no light-theme selected state below 1.2:1.

Visual QA gate: the full route set at 390, 768, 1440 in both themes. Rollback
risk: low for tokens, medium for mobile editing removal. Ship mobile removal
behind that phase's PR so it can be reverted alone.

## 9. Test strategy

Four layers, all runnable without live SermonAudio or workers.

| Layer | Command | Owns |
|---|---|---|
| Unit and component | `npm test` (vitest) | lifecycle table, primitives, page behaviour through props, fixtures |
| Playwright interaction | `npm run visual` (adds `tests/visual/interaction`) | hit targets, primaries, keyboard, dialogs, tabs, titles, validation, toasts, lifecycle labels |
| Visual snapshots | `npm run visual` | layout drift on the route set x 3 viewports x 2 themes |
| Accessibility | `npm run a11y` | axe WCAG 2.2 AA on 6 routes x 3 viewports x 2 themes |

Add `@axe-core/playwright` as a dev dependency. It is the only new dependency
and it exists so the `visual-qa` agent's axe claim has deterministic backing.

`playwright.config.ts` keeps `reducedMotion: "reduce"`; theme comes from the app
toggle so the existing snapshot approach works. Projects stay `mobile`,
`tablet`, `desktop`. Add a fourth project or `test.describe` override for the
1024 two-column case.

### Named regression tests

| ID | Spec | Assertion |
|---|---|---|
| UI-01 | `interaction/ui01-menu.spec.ts` | Open `[data-testid="library-actions-s-01"]`, `elementFromPoint` each `[role="menuitem"]` returns that item; click `Preview`, path and `h1` stay on `s-01`. Repeat on the last row at 390x568; panel bottom `<= innerHeight`. |
| UI-01b | same | Open a menu, press Tab, assert it closed or focus stayed inside; Escape returns focus to the trigger. |
| UI-02 | `interaction/ui02-primary.spec.ts` | `[data-testid="approve-primary"]` intersects the viewport at 390x844, 768x1024, 1440x900 with `scrollY === 0`; count of accent-filled visible controls is 1. |
| UI-03 | `interaction/ui03-validation.spec.ts` | Fresh `/new`: zero `role="alert"`, zero `aria-invalid`, zero live-region mutations. Blur each empty required field: its message appears with `aria-describedby`. |
| UI-04 | same | Dropzone contains no nested interactive; the file input is not a tab stop. |
| UI-06 | `interaction/settings-save.spec.ts` | At every 200px scroll step at 390 and 1440, at most one `div.sticky` save bar is visible; its button is not `bg-accent`; its label contains the section name; a clean section renders none. |
| UI-09 | `interaction/activity-filters.spec.ts` | Filter chips expose `aria-pressed`, selection changes the list, URL reflects `?state=failed`, `/activity/job-1037` opens expanded. |
| Tabs | `interaction/tabs.spec.ts` | One tab stop per tablist; ArrowRight moves focus and selection; every `aria-controls` resolves; Home/End work; `?tab=files` restores. |
| Route title and focus | `interaction/route-title-focus.spec.ts` | After navigation, `document.title` starts with the route label; `document.activeElement` is the `h1` or `main`. Teaching route title contains the teaching title. |
| Lifecycle labels | `interaction/lifecycle-labels.spec.ts` | For each fixture id, the chip text is identical on `/`, `/library` and `/teaching/:id`; a DOM sweep finds no label outside `Draft, Needs review, Processing, Ready to publish, Published, Failed`. |
| Needs review count | `interaction/inbox.spec.ts` | Nav count equals `counts.needs_review`; opening the section lists exactly those records; after approve the count drops by one. |
| Activity retry | `interaction/activity-retry.spec.ts` | Failed row `Retry` sends one POST, a queued row appears with the new id, toast carries the id; `View teaching` navigates to the linked teaching. |
| Mobile workspace | `interaction/workspace-mobile.spec.ts` | At 390: no timeline jump/zoom, no cut switches, no exact times; `Approve & upload` visible at `scrollY = 0`; Details opens a `role="dialog"` with a trap and focus return. |
| Toast queue | `interaction/toast.spec.ts` | Four pushes keep four; undo toast has `Undo` and `Dismiss`; error toast does not auto-dismiss; toast clears the sticky bar. |
| Touch targets | `interaction/touch-targets.spec.ts` | Every visible `button, a, summary, [role="tab"], [role="switch"], [role="slider"]` in `main` at 390 is at least 44x44. |
| Axe | `a11y.spec.ts` | No serious or critical findings across the matrix. |

`visual-qa` runs after every UI batch (per `docs/UI_CORRECTIONS.md` and
`.opencode/agents/visual-qa.md`) and must cite the matching spec for each
finding. A finding without a deterministic test is added to the phase's task
list before ship.

## 10. Risks, conflicts, open questions, backlog

### Audit conflicts, resolved

| Conflict | Resolution |
|---|---|
| Code-health report says the light theme and the visual suite are absent | Wrong. `web/tests/visual/screens.spec.ts` runs 6 routes x 2 themes across the three viewport projects (36 screenshot tests) and `responsive.spec.ts` checks 4 widths. The real gap is interaction and axe coverage. Do not repeat the missing-theme or missing-suite claim. |
| 03-responsive and 09 keep mobile editing; 09 Concept C removes it | Remove on mobile. The timeline traps scroll and the primary is 824px down. Mobile reviews and approves; desktop edits. |
| 01 keeps `Recent teachings` at 3 rows; 09 removes Home | Remove. Inbox is the queue, not a lower-fidelity Library. |
| 01 proposes `Needs a plan` as a sixth label; 05 proposes `Rendered (local)` | Six labels in §4; a no-plan record is `Draft` with `Run cut detection`. |
| UI-03 says keep `Start processing` disabled and also "submit the empty form shows errors" | Keep it disabled (repo doc wins). Validate on blur, and give the disabled primary `aria-describedby` naming the missing fields. The acceptance test is rewritten accordingly. |
| Code-health says split `SermonReview` before redesigning; 09 puts the sticky bar first | Both. Phase 0 adds the bar as a container (small, shippable), Phase 3 does the extraction. |

### New facts that change the plan

- `pending_review` is never written to `sermons.edit_status`. Without the two
  writes in `ui/job_executors.py` and the plan status on the list item, the
  queue would be empty for exactly the records it exists to show.
- `useBlocker` needs a data router. `App.tsx` uses `BrowserRouter`, so Phase 2
  migrates to `createBrowserRouter` before the unsaved guard can work in-app.
- `ui/job_queue.py:1043` already has `retry_job`; only a route is missing.
  Retry is cheaper than the audits assume.
- `publish_dry_run_sermon` exists with no route. Drafts need that route, not a
  redesign of the draft state.

### Risks

| Risk | Mitigation |
|---|---|
| `ui.tsx` change breaks every screen | Primitive unit tests plus the interaction specs before merge; one owner per batch |
| Route churn breaks bookmarks and the old snapshot set | Redirects for `/library/:id`, `/jobs`, `/jobs/:id`; snapshots updated only in the phase that invalidates them |
| Lifecycle derivation drifts between TS and the Python `state` filter | One fixture table, two test suites reading it |
| Mobile approval publishes to a live account | Phone approval is one tap from the review; keep `Approve & upload` behind the existing confirm-free path but show kept duration, cut count and destination in the bar. Revisit if phone publishing is not acceptable |
| Empty Inbox in a quiet week | Real empty state with next run and one secondary action; counts still show Published and Drafts |
| Retry and publish-draft cannot be validated in CI | Mock them deterministically and mark live checks manual in the PR |
| Settings split changes deep links | Redirect `?section=general` to `/settings/preferences` |

### Open questions

1. Is phone publishing acceptable, or should mobile only `Send back`? Default in
   this plan: allowed.
2. Weekly volume. If most weeks produce one teaching, the Library archive and
   the empty Inbox deserve more design weight than the queue.
3. Do published records need a separate mode at all, or is the workspace with a
   publication tab enough? Plan assumes one route, two modes.
4. Does the demo build ship, or is it a development harness? If it ships, every
   live-only control needs a disabled state with a reason.
5. Should drafts appear in the Inbox at all? Plan: yes, as the last section, not
   in the needs-review count.

### Backlog, deliberately not planned

Autosave Settings with undo; bulk selection and bulk publish; CSV scope picker
and formula escaping; FTS transcript search; list virtualisation; a `DemoBridge`
adapter to delete the 39 `isLive` branches; command palette and keyboard
shortcuts; account switcher; post-publish analytics; split-console inspector;
jobs dock; shipping a webfont; replacing `@types/react` 19 with 18 and adding
ESLint.

## 11. Recommended first batch

Start Phase 0. Four tickets, four disjoint file sets, all mergeable
independently. Branch off `release/v1.9.4`.

| Ticket | Owner files | Scope | Tests |
|---|---|---|---|
| `fix/ui-01-menu-portal` | `web/src/components/ui.tsx` | Portal, fixed positioning, flip and clamp, close on focusout, `shadow-menu` | new `web/src/components/ui.menu.test.tsx`, `web/tests/visual/interaction/ui01-menu.spec.ts` |
| `fix/ui-02-review-primary` | `web/src/components/SermonReview.tsx` | Sticky bar, single primary, secondary `Save details`, compressed status strip, remove duplicate approve block | `SermonReview.test.tsx` updates, `interaction/ui02-primary.spec.ts` |
| `fix/ui-03-new-teaching-intent` | `web/src/pages/NewSermon.tsx` | Single dropzone control, secondary `Choose file`, touch-gated validation, inline errors, drop fake tabpanel, file input out of tab order | `NewSermon.test.tsx` updates, `interaction/ui03-validation.spec.ts` |
| `feat/lifecycle-fields` | `server/api/schemas.py`, `server/api/routers/sermons.py`, `ui/database.py`, `ui/job_executors.py`, `tests/unit/test_sermons_api.py` | `edit_status`, `upload_status`, `plan_status` on list items; counts; `pending_review` writes | new `tests/unit/test_sermons_api.py` cases |

Second batch, ready when the first merges: `chore/a11y-gate` (`playwright.config.ts`,
`package.json`, `tests/visual/a11y.spec.ts`, `ui.tsx` skeleton labels,
`toast.tsx` host), `feat/route-titles` (`routes.ts`, `App.tsx`, `Shell.tsx`),
`feat/lifecycle-helper` (`utils/lifecycle.ts` plus mock fixture rewrite), and
`fix/demo-waveform` (`api/hooks.tsx`).

Each ticket: `npm test`, `npm run build`, the named interaction spec, then a
`visual-qa` run on the routes it touches. PR body lists the audit item, the test
that now covers it, and any manual-only check.
