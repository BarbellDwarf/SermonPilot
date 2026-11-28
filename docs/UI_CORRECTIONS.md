# UI Corrections

Open items from the React console review at commit `d4d2532`. Scope is `web/`.
The legacy Streamlit UI has been removed; see
[Legacy Streamlit removal](#legacy-streamlit-removal).

Baseline test status: `npm run visual` passed 108/108, but the suite only takes
static screenshots and checks overflow. Every blocker below passed that suite.

Severity:

- **P0**: opens the wrong record, hides the main action, or misleads on load.
- **P1**: accessibility failure, ambiguous destructive or save action, or broken
  keyboard/touch behavior.
- **P2**: consistency, density, copy, and polish.

If a correction needs a structural change, take it. Navigation, row anatomy,
the Review layout, and the Settings save model may be redesigned. Keep
`web/DESIGN.md` and the visual tests in the same PR as the change.

## P0

### UI-01 Library row menu opens the wrong teaching

The row `⋯` menu is painted under the following rows. Clicking `Preview` on
Sample Teaching 1 opened `/library/s-03`, `h1` "Sample Teaching 3".
`elementFromPoint` over both menu items returned the next row's full-card link,
not the menu item. Keyboard `Enter` works, which is why screenshots and keyboard
tests missed it.

Cause: `SermonRow` in `web/src/pages/Library.tsx` places a full-row
`absolute inset-0` link above the row, while `Menu` in
`web/src/components/ui.tsx` renders an absolute `z-40` panel inside the row.
Each animated `li.stagger-item` creates its own stacking context, so the menu
cannot rise above later sibling rows.

Required:

- Render the menu panel in a portal to `document.body`, or otherwise move it
  outside the row stacking context. If a portal is used, keep outside-click,
  Escape, and focus-return behavior in the same component.
- Add viewport flip or clamp. At 390x568 the last row menu ran to `y=574` and
  was covered by a link.
- Keep the full-row link from covering any open menu or action control.

Acceptance test:

- Open the menu on the first Library row, assert `elementFromPoint` over each
  item is that item, click `Preview`, and assert the URL and heading stay on the
  same sermon.
- Open the last row menu at 390x568 and assert the panel is inside the viewport
  and hit-testable.

### UI-02 Review page hides the primary action below the fold

At 1440x900, `Approve & upload` was at `top=1336`, 436px below the fold.
`Save details` was also `bg-accent` at `top=896`. Two primaries compete, and
Review has no sticky action bar, unlike New teaching.

Required:

- Add a sticky Review action bar with `Approve & upload` as the only primary.
- Make `Save details` secondary. It is a section save, not the page action.
- Compress the status strip. Current copy:
  `CUT PLAN: PENDING REVIEW / Teaching status: RENDERED / Revision 2 of 3 · 87% confidence · No problems found · Cuts found automatically`.
  Keep status, confidence, and problems; drop duplicated state.
- Keep the action bar above the mobile bottom nav and clear of the safe area.

Acceptance test:

- At 1440x900 and 390x844, `Approve & upload` is visible without scrolling and
  is the only accent-filled primary on the page.

### UI-03 New teaching announces errors before interaction

Initial load renders `role="alert"` "Choose a file to upload." and the helper
`Missing: source file, title, speaker, date.` A screen reader hears a failure on
arrival. Title, speaker, and date have no inline error and no `aria-invalid`.

Required:

- Track whether a field or the form has been touched or submitted. Do not render
  errors before that.
- Show inline messages for title, speaker, and date, tied to the input with
  `aria-describedby`, and set `aria-invalid` while invalid.
- Keep the bottom missing-items summary, but make it descriptive until submit.
- Keep `Start processing` disabled until valid.

Acceptance test:

- Fresh `/new` has no `role="alert"` and no `aria-invalid`.
- Submitting the empty form shows inline errors and moves focus to the first
  invalid field.

## P1

### UI-04 Nested interactive dropzone

Axe reports `nested-interactive` (serious) on `/new`: a `div role="button"`
dropzone contains the focusable primary button `Choose file`.

Required: remove `role="button"` from the wrapper, or remove the inner button
and make the wrapper the only control. One click target, one accessible name.
Make `Choose file` secondary so `Start processing` is the page primary.

### UI-05 Fake source tabs

The Upload, Server, and Cloud panels use `role="tabpanel"` with no tablist or
tab controls. Use a real tablist with roving tabindex and `aria-controls`, or
drop the tab roles and use plain switchable sections.

### UI-06 Settings save model is ambiguous

Desktop shows at least three accent `Save` buttons. On mobile, scrolling showed
three sticky save bars at once (`top=112`, `498`, `711`), all labeled `Save` or
`Saved`, none naming its section. This violates the one-primary rule in
`web/DESIGN.md` and makes the target unclear.

Required:

- One save surface per dirty section, secondary styling, label that names the
  section (`Save appearance`, `Save processing options`).
- Show a bar only when its section is dirty. Do not stack multiple bars.
- Keep the unsaved-changes guard when leaving.

Acceptance test:

- At 390x844, at most one save bar is visible at every scroll position.
- No section save uses primary styling.

### UI-07 Skeleton has a prohibited ARIA attribute

`web/src/components/ui.tsx:554` and `:569` put `aria-label="Loading"` on
`aria-hidden` generic `div`s. Axe reports `aria-prohibited-attr` on every route.

Required: remove the `aria-label`. Keep `aria-hidden`. If loading needs an
announcement, use a live region with text, not a label on a hidden div.

### UI-08 Touch targets below 44px

Violations found at 390x844:

- Review jump buttons `Opening`, `Middle`, `Closing`: 36px high.
- Review zoom `Fit`, `2m`, `1m`, `30s`: 32x36 to 36x36.
- Review tabs `Transcript`, `Files`, `Previews`, `History`: 40px.
- New teaching `Output location` summary: 16px high.
- Review `Exact times` summary: 20px high.
- Settings theme radios: 13x13 input, even though the wrapping label may be
  larger. Verify the effective hit area, not the input alone.

Required: 44x44 minimum for every interactive control, per `web/DESIGN.md`.
Icon-only controls need `aria-label` and `title`.

### UI-09 Jobs tabs have incomplete semantics

The tablist sets `aria-selected` but every tab is tabbable, no tab has
`aria-controls`, and there is no `tabpanel`. `ArrowRight` changes selection while
focus stays on the previous tab.

Required: roving tabindex, `aria-controls` to a `tabpanel`, and focus follows
selection. `ArrowLeft`, `ArrowRight`, `Home`, and `End` move between tabs.

### UI-10 Static page title

`web/index.html` hardcodes `SermonPilot Console` on every route.

Required: set a per-route title, for example `Library · SermonPilot`,
`Settings · SermonPilot`, and the teaching title on Review.

### UI-11 Demo Review requests a live waveform and logs a 404

Opening `/library/s-01` in mock mode requests
`/api/media/sermons/s-01/waveform` and logs a 404. The page still renders a mock
waveform.

Required: skip remote media requests when `!isLive`, or serve the mock asset.
Leave the visible explanation that preview is live-only.

## P2

### UI-12 Row anatomy differs between Home and Library

Home puts the status chip on the left of recent teaching rows. Library puts it
on the right. Pick one anatomy and reuse it. Status should read in the same
place on every teaching row.

### UI-13 Home density and stat labels

Pipeline health rows are 88 to 89px tall for one line. Recent rows are 56 to
57px. Tighten health rows or give them a second line of real information.

`Active jobs 2` and `Queued 1` double count queued work inside active. Rename to
`Running` and `Queued`, or show one total with a breakdown.

### UI-14 Repeated New teaching CTA

`New teaching` appears as a primary in the Home, Library, and Jobs headers, and
the mobile bottom nav repeats `New`. Choose one entry point per viewport. Use the
same label on mobile and desktop.

### UI-15 Library search is contiguous substring only

Typing `Sample 2` returns zero rows because `Sample Teaching 2` does not contain
the contiguous string. Tokenize the query on whitespace and match every token
across title, speaker, and series.

### UI-16 Light theme surface separation is weak

Page and cards are both near-white and rely on 1px borders. Contrast passes, but
surfaces do not separate at a glance. Darken the light page background or raise
the card surface a step so the card edge is not the only cue.

### UI-17 Review is visually dense

The cut plan repeats a danger-outline `Remove` for every cut, next to a switch.
`Restore original` is another danger outline. Group secondary cut actions in a
menu, or use a single danger action for the selected cut. The timeline selection
is subtle in dark mode; check it against the surrounding rail.

### UI-18 Demo dropzone ignores a real file

Clicking the whole dropzone in demo mode selects
`sample-sermon-upload.mp3`; a dropped real file is ignored. Make the demo
behavior explicit in the copy, or accept a real file and keep the mock only for
the demo button.

## Legacy Streamlit removal

Completed. `ui/` now holds only backend modules that the console API, worker,
CLI, and tests import. Presentation files and dependencies are gone.

Removed:

- `streamlit_app.py`, `ui/pages.py`, `ui/shared_navigation.py`,
  `ui/ui_state.py`, `ui/ui_processor.py`
- `ui/ui_pages/**`
- `ui/components/` (all four audio widgets plus its package init)
- the root and `ui/` Streamlit config directories, `ui/README.md`, and
  `ui/requirements-ui.txt`

Kept:

- `ui/database.py`, `ui/job_queue.py`, `ui/job_executors.py`,
  `ui/job_worker.py`, `ui/config_utils.py`, `ui/sermonaudio_api.py`,
  `ui/sermonaudio_accounts.py`, `ui/sermonaudio_analytics.py`,
  `ui/sermon_importer.py`, `ui/sermon_metadata.py`, `ui/sermon_manager.py`,
  `ui/upload_only.py`, `ui/version.py`, `ui/system_status.py`,
  `ui/performance_monitor.py`, `ui/analytics_manager.py`, `ui/media_server.py`,
  `ui/auth.py`, `ui/job_labels.py`, `ui/auto_edit_apply.py`.
- Streamlit imports and widget code were stripped from `ui/auth.py`,
  `ui/config_utils.py`, and `ui/sermon_metadata.py`; the API and tests keep
  the remaining token, config, and metadata-cache functions. The startup
  trash/job sweep moved from `streamlit_app.py` to `ui/job_worker.py`.

Also completed:

- `pyproject.toml`: removed the `streamlit` dependency and the
  `streamlit_app.py` script entry; `python-multipart` is now an explicit
  dependency because FastAPI uploads previously got it transitively from
  Streamlit.
- `requirements/requirements.txt`, `docker-compose.yml`, and `.env.example`
  lost their Streamlit entries.
- `docker/nginx/nginx.conf` now proxies the console/API on port 8504.
- `server/api/routers/meta.py` returns `console_ready` instead of
  `streamlit_ready`; the console client was updated with it.
- `AGENTS.md`, `README.md`, `docs/README.md`, and the Streamlit-era guides
  were updated or marked historical. Historical release notes remain.
- Streamlit page tests were removed; shared backend tests were kept and the
  helpers that lived in page modules were retargeted at
  `ui.auto_edit_apply`.

Acceptance:

- `rg -i streamlit` returns only historical release notes and intentional
  compatibility references.
- The image builds without Streamlit installed.
- `pytest` passes.
- The container serves the React console and `/api/` with no Streamlit process.
- No server or worker import points at a deleted module.

## Visual QA gate

Project agent: [`.opencode/agents/visual-qa.md`](../.opencode/agents/visual-qa.md).

Run the `visual-qa` subagent:

- after every UI PR, before marking it complete
- after every batch of three or more corrections in this document
- at the release cut, against the release branch

The agent must use mock mode, cover `/`, `/new`, `/library`,
`/library/s-01`, `/jobs`, and `/settings` at 390x844, 768x1024, and 1440x900,
in dark and light. It checks:

- stacking order and z-index fights, including open menus over rows
- `elementFromPoint` hit targets for every menu item and row action
- alignment, spacing, and row anatomy
- clipping, overflow, and elements outside their containers or the viewport
- sticky and fixed bars overlapping content, each other, or the bottom nav
- incorrect button placement, duplicate primaries, and missing labels
- focus visibility, keyboard order, Escape behavior, focus return
- axe WCAG 2.2 AA: no serious or critical findings
- console errors and failed requests
- text truncation and controls under 44x44

A pass is invalid if it only inspects screenshots. Every finding needs a route,
viewport, theme, selector, measured rects or overlap, screenshot path, expected
rule from `web/DESIGN.md`, and a suggested fix with the test that would catch it.

## Completion checklist

- [x] UI-01 Library menu hit target and viewport clamp
- [x] UI-02 Review sticky primary action
- [x] UI-03 New teaching validation on interaction only
- [x] UI-04 Dropzone nested interactive removed
- [x] UI-05 Source tabs use valid ARIA
- [ ] UI-06 Settings save surfaces disambiguated
- [x] UI-07 Skeleton ARIA fixed
- [ ] UI-08 All touch targets at least 44x44
- [ ] UI-09 Jobs tabs complete
- [x] UI-10 Per-route titles
- [x] UI-11 Demo waveform 404 removed
- [x] Deterministic axe gate in the visual suite
- [ ] UI-12 Row anatomy unified
- [ ] UI-13 Home density and stat labels
- [ ] UI-14 Single New teaching entry point
- [ ] UI-15 Tokenized Library search
- [ ] UI-16 Light theme surfaces separated
- [ ] UI-17 Review density reduced
- [ ] UI-18 Demo dropzone behavior documented
- [x] Legacy Streamlit removal complete
- [ ] Visual QA pass on 390, 768, and 1440, dark and light
- [ ] Final QA pass at the release cut
- [ ] `npm run build`, `npm test`, and `npm run visual` pass
- [ ] No serious or critical axe findings

## QA log

| Date | Commit | Agent | Result | Evidence |
| --- | --- | --- | --- | --- |
| 2026-11-27 | `d4d2532` | parent review | 18 open items, 3 P0 | parent review evidence |
| 2026-11-27 | `37f0724` | phase 0 | UI-01 to UI-05 and UI-07 fixed; 249 vitest, 127 Playwright passed, 8 skipped, axe clean on 24 runs | PR #406 |
| 2026-11-27 | `100c0b2` | phase 1 | UI-10 and UI-11 fixed; route titles and focus verified; 36 axe checks, 300 vitest, 163 Playwright passed, 8 skipped | PR #407 |
