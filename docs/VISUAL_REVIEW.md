# Visual review, round 1

A browser pass over the built console, driven with Playwright against the real
API bridge and a seeded database so every page had records on it.

## What was rendered, and how

The console was built in `live` mode (`VITE_API_MODE=live`), served, and driven
with Playwright against `google-chrome`. The API bridge ran on `127.0.0.1:8504`
against a throwaway SQLite database holding seven teachings across all four
states, five background jobs across all five states, two plan revisions, and real
files on disk so `hasRender` was true.

88 screenshots: 17 pages at 1440x1000 and 390x844 in both themes, plus the two
empty states and the two extra job tabs. They are in
`web/validation/visual-r1/`, alongside `round2-report.json`, the machine-readable
output of the automated checks.

Every page listed below was rendered and looked at. Nothing here is inferred from
the code alone. Where a measurement disagreed with what the screenshot showed,
the measurement is called out as wrong rather than the page.

### Two measurement errors worth recording

Both were found by looking at a screenshot and then measuring, not the other way
round.

**Contrast.** The first pass reported 52 contrast failures, all in light theme on
two Settings tabs. Every one was a false positive from the checker: it walked up
for an opaque background, found none (the wrappers are transparent), and fell
back to black, then compared dark-theme text against a light-theme page. Fixed in
the harness; zero real failures on the re-run. Separately, the harness reported
`Reset task` at 3.16:1 in light theme, which was reading `--danger` before the
theme class had been applied, because the button sits inside a closed `<details>`
that the harness had not opened. Once opened it measures `rgb(194, 47, 61)` on
white, 5.9:1. **No contrast defect exists in this console.**

**Clipping.** 88 "clipped" hits, 88 of which were the same `sr-only` skip link
and the screen-reader-only labels on the Library filters. Clipping those is what
they are for. The harness now skips them. **No clipping defect exists.**

After both fixes the automated pass reports zero findings, which means the
remaining findings below are ones the harness is not looking for.

## Home

| # | Severity | Finding |
|---|----------|---------|
| 1 | blocker | The same queued job was listed twice, under Active jobs and again under Up next. `useHomeData` put `queued` in both lists. Two rows, same job id, no way to tell them apart. |
| 2 | blocker | The summary counts disagreed with the lists. "Teachings 4" was `recentSermons.length`, and `recentSermons` is `recent.slice(0, 4)`, so a 7-record library reported 4. "Waiting for you 2" counted drafts only while the list below showed 3 rows (2 drafts and a failure). A stat that cannot be reconciled with the list under it is worse than no stat. |
| 3 | blocker | On a queued job the duration column read `running`. `mapping.job_duration` returns that string for a job with no `completed_at`, so the row said `running` for something that had not started. |
| 4 | should-fix | Needs you truncated the title: `Ruth 2 (Re-recorded)` → `Rut…` at 390px. The title is the only thing on the row worth reading. |
| 5 | should-fix | The AI provider warning card carries a raw model URI (`hf.co/unsloth/qwen3.8-27b-gguf:UD-Q2_K_XL,ornith-1.5:9b…`). It is server-supplied detail text, not console copy, and it is four lines of it. |
| 6 | nit | The meter bar on the left of each status card is a coloured sliver at 3px. It reads as a border rather than a proportion. |

## New teaching

| # | Severity | Finding |
|---|----------|---------|
| 7 | blocker | The start button sat 1406px down a 1547px page, so at a 1000px viewport it was below the fold and the operator had to scroll the whole form to find out whether they could start. The "Still needed" line was with it, at 1370px. |
| 8 | nit | The `Reset` button in the header is a ghost variant with no border. Next to `New teaching` on other pages it is the same shape as a disabled control. |

## Library

| # | Severity | Finding |
|---|----------|---------|
| 9 | blocker | Card interiors were ragged. Measured heights across one grid: 190, 190, 190, 208, 208, 208, 160. The 48px spread came from the title wrapping to one or two lines with no reserved height, so cards in the same visual row did not line up. |
| 10 | blocker | The status chip row wrapped. On the two draft cards "Waiting for you" broke onto two lines and pushed the duration down, so the duration sat on a different baseline in every card in the grid. |
| 11 | blocker | A teaching with no series rendered an empty bordered box: the series `<span>` was unconditional, so it drew its border and padding around an empty string. Visible as a 14x6px stub next to the Guest Service card's status chip. |
| 12 | should-fix | The empty-search state said "Try a different search term, or clear the search" and offered no way to clear it from there. The `Clear` button was above, next to the status filter. |

## Library detail

| # | Severity | Finding |
|---|----------|---------|
| 13 | blocker | A record in `queued` or `draft` state with nothing rendered offered "Push to SermonAudio" as its primary action. `sermonActionMatrix` gated the legacy push on `status !== "draft"` but not on a render existing, so the button led to a request with no file behind it. |
| 14 | should-fix | The uploaded timestamp rendered as raw ISO: `2026-09-27T22:41:00`. Every other timestamp in the console goes through `fmtStamp`. |
| 15 | should-fix | Scripture rendered twice on one record: `Ruth 1:1-18` under a "Scripture" heading, then `Ruth 1:1-18` again immediately below with no heading. `bible_text` and `scripture_reference` held the same string and both were printed. |
| 16 | should-fix | A queued record's page is one 120px card and then 850px of empty space. The "Watch it under jobs" button is inside the card, so the page reads as broken rather than as waiting. |

## Jobs

| # | Severity | Finding |
|---|----------|---------|
| 17 | blocker | The API returns a reason for every failed and cancelled job (`error`, populated in both cases) and the console discarded it. `toJob` dropped the field. The Failed tab showed a red FAILED chip and nothing else: "SermonAudio rejected the upload: file larger than 500 MB after normalization" was in the response and never reached the screen. This is the single worst thing in the pass. |
| 18 | blocker | Cancelled runs were counted as failed. `partitionJobs` folded `cancelled` into the `failed` array, so the tab said "Failed 2" over one genuine failure, and the success rate counted an operator's deliberate stop against the pipeline. |
| 19 | blocker | A draft with an unreviewed plan offered "Push to SermonAudio" from the header, on the same screen that carries the review decision. The upload could go out over cuts nobody had approved. |
| 20 | should-fix | The Failed tab's empty state promised "Failures land here with a Retry button next to each one." The live console has no Retry button, and the card next to the failed row says so in as many words. |
| 21 | should-fix | The metadata line truncated at desktop width too, not just mobile: `job-1044 · created Sep 28, 20:13 · finished Sep 28, 20:21 ·` with the duration cut off. Measured 303px of content in a 264px box. |
| 22 | should-fix | The header said "Refreshes every 5 seconds." Implementation detail in operator-facing copy, and it contradicted the row beneath that says the list updates itself. |

## Settings

| # | Severity | Finding |
|---|----------|---------|
| 23 | blocker | Three of ten tabs were unreachable. The tab strip was `overflow-x-auto` with `scrollWidth` 1416 against `clientWidth` 1152 at 1440px. Appearance & Account, Users and System sat off the right edge with no scrollbar visible and no wrap, so an operator could not find the Users tab at all. At 1024px it was five tabs missing. |
| 24 | blocker | On the System tab the "AI provider" row overlapped itself: the label span measured 0px wide while the detail span wrapped under it, so "Model "unknown" not available" printed straight through the label. `min-w-0 flex-1` on a flex row with no width to divide. |
| 25 | blocker | The Backup tab rendered the mock snapshot on a live console. `"sermons": 5`, `"Sample Teaching 1"`, three "(mock)" history rows, and "Mock snapshot list" in the copy, all served by a server with 7 records. A real operator would read the mask as their data. |
| 26 | should-fix | `Reset to defaults` on the Backup tab was a live button that could not work, and its confirm dialog said so. On a real server it would have looked like a working destructive control. |
| 27 | should-fix | "Theme applies instantly in this mock and persists on save" told the operator two contradictory things, and the theme did not survive a reload. The header toggle and these radios each held their own copy of the value. |

## Cross-cutting

| # | Severity | Finding |
|---|----------|---------|
| 28 | blocker | The theme reset on every reload. Measured: `dark` → toggle → `light` → reload → `dark`. The value lived in a `useState(true)` in `App`. |
| 29 | should-fix | At 390px the `Logout` label and the theme toggle overlapped by 18px. The header row is `min-w-0` with no wrap, so the two children were squeezed into the same space; the label rendered clipped to "Logou". |
| 30 | nit | Every job row's action cluster is `Cancel` and `Delete` at the same weight and colour on non-running jobs. Two destructive-looking buttons side by side. |

## What was fixed in code

All 18 blockers and the 8 should-fix items above are fixed. Tests were added
for each behaviour that could regress silently, and the numbers are in the
commit message.

## Left for River's eyes

1. **The Library card grid.** The series name moved out of the chip row and into
   the metadata line to stop "Waiting for you" wrapping. That is the one change
   that moved information rather than removing it, and it reads differently from
   how the cards looked before.
2. **The New teaching sticky bar.** The start button and the outstanding
   requirements now sit in a bar stuck to the bottom of the viewport. It works
   at both widths and both scroll positions, but a permanently visible bar is a
   new shape for this console and worth a look.
3. **Cancelled as its own Jobs tab.** Four tabs instead of three. The alternative
   was leaving cancelled inside Failed, which is what finding 18 was about.
4. **The Backup tab now says there is nothing to see** on a live server. Whether
   a real snapshot history should exist is a backend question this pass cannot
   answer.
5. **The AI provider card still shows the raw model URI** (finding 5). Fixing it
   means changing what `system_status.py` sends, which is beyond a visual pass.

## Unverified

- **No real audio was played.** The seeded media files are byte patterns, not
  audio, so every player, the cut timeline and the audio-offset maths were
  verified as rendered layout only. Their behaviour with real media is not
  covered here.
- **The light theme was checked for contrast, not for colour temperature.** It
  measures correctly against WCAG AA, but whether it reads as a considered light
  theme rather than an inverted dark one is a judgement call.
- **Print styles, high-contrast mode, and 200% browser zoom were not rendered.**
- **The Python suite did not run.** The host has no GPU or whisper dependencies,
  so the console changes are gated on tsc, vitest and the build only.