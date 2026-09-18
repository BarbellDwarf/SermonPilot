# SermonPilot Console (web/)

Mock-first rebuild of the SermonPilot UI. The Streamlit app stays live; everything new lands here.

## Stack

React 18 + Vite 5 + TypeScript (strict) + Tailwind CSS 3 + shadcn-style local primitives (`src/components/ui.tsx`) + TanStack Query. React Router routes; mock data in `src/mock/data.ts`, live data via the read-only FastAPI bridge (`server/api/`).

## Modes

The app builds twice from the same source. The mode is baked in at build time via
`VITE_API_MODE` (`mock` default, `live` optional) and `VITE_API_BASE`:

```bash
cd web
npm run build                                            # mock bundle into dist/
VITE_API_MODE=live VITE_API_BASE=http://127.0.0.1:8504 npm run build   # live bundle
```

- **Mock mode** (`npx vite preview --port 4173`): all data from `src/mock/data.ts`,
  brief artificial loading, local-only actions with `(mock)` toasts and confirms.
- **Live mode** (FastAPI bridge serves the live bundle + `/api/*` on port 8504):
  read-only TanStack Query hooks (`src/api/hooks.tsx`, 5–15 s staleTime, 5 s jobs
  poll). Mutating actions stay hidden; the failed-job Retry explains the read-only
  bridge via toast. The header badge reads `live` or `mock` accordingly.

## Validation

Phase 4b harness (headless Chrome over CDP, viewports 1680x1050 and 390x844):

```bash
# fixture DB with fictional rows only (Sample Teaching 1..5, one failed job,
# one applied_local plan)
.venv/bin/python /tmp/opencode/phase4b_fixture.py  # writes /tmp/opencode/phase4b_fixture.db
SERMONPILOT_DB=/tmp/opencode/phase4b_fixture.db PORT=8504 \
  .venv/bin/python -m uvicorn server.api.app:app --host 127.0.0.1 --port 8504
```

What was checked per page (`/`, `/library`, `/library/:id`, `/jobs`, `/new`,
`/settings`, both modes, both widths):

- Zero horizontal overflow (`scrollingElement.scrollWidth <= innerWidth` at 390px).
- Tap targets: every button/link ≥ 44px (radios/switches measured by their
  full-row label, which is the real hit area); skip-link exempt.
- Keyboard: every interactive element `.focus()`-reachable, no positive
  `tabindex`, visible `:focus-visible` ring from the accent token.
- Contrast: every text token vs its backgrounds from computed CSS vars, dark and
  light themes (AA 4.5+; this pass darkened light-theme `--warn` to `#8a5a05`).
- Empty states: library no-match, jobs tabs, home queue, missing plan, missing
  transcript/files all render directive copy with a next action.
- Interactions: live search/sort filter, job tabs + failed Retry toast, review
  form parses `mm:ss.s` and seconds with live duration + blocking errors, mock
  approve transitions plan state, toasts appear, confirms block, drawer opens at
  390px, deep link `/library/:id` loads directly in live mode.

Full captures land in `web/validation/phase4b/` (gitignored); four representative
shots are committed: live home, live detail (applied_local plan), live failed job
with Retry, live library in the light theme.

## Design tokens

`src/index.css` holds the source of truth as CSS custom properties; `tailwind.config.js` maps them (`ink`, `surface`, `raised`, `line`, `mist`, `muted`, `accent`, `ok`, `warn`, `danger`, `info`).

- Base: tinted ink neutrals, dark theme default, light theme via `.light` on `<html>`.
- Accent: single violet (`--accent`), used for primary actions, focus rings, selected-tab dot.
- Semantic: green ok, amber warn, red danger (failure + destructive only), sky info.
- Type: system sans for UI, system mono for ids/durations/logs. Scale 12/13/15/17/22/30.
- Radius: 6/10/14/20. Signature motif: level-meter bar on status cards.

## Phase plan

- Phase 1 (this): scaffold, tokens, shell (sidebar + mobile drawer), Home + Jobs screens, placeholders for New Sermon / Library / Settings. All mock data in `src/mock/data.ts`.
- Phase 2: real routing + backend wiring (New Sermon form, Library data, live job status).
- Phase 3: auth, settings persistence, upload progress, polish.

## Settings coverage (legacy Streamlit -> web console)

`ui/ui_pages/settings.py` (8 tabs) maps to `src/pages/Settings.tsx` sections as:

- General -> General (processing options + output settings). SermonAudio API
  key / broadcaster ID from that tab live under SermonAudio Accounts instead.
- LLM -> LLM Providers (`LlmConnections.tsx`, pre-existing).
- Embeddings -> INTENTIONALLY OMITTED. Removed by decision; do not rebuild.
- Audio -> Audio Processing (`AudioSettings.tsx`).
- Transcription -> Transcription (`TranscriptionSettings.tsx`).
- Validation -> Validation (`ValidationSettings.tsx`).
- Advanced (YAML Backup & Restore) -> Config Backup & Restore
  (`ConfigBackup.tsx`, masked view + mock download/upload-apply + mock
  history). The SQL Config Manager sub-tab has no web equivalent and is not
  ported; the mock history list stands in for it.
- Templates -> Prompt Templates (`PromptTemplates.tsx`).

All new sections are mock state only (per-section save + dirty-state + toast,
confirms on destructive reset/apply). Captures:
`web/validation/settings-coverage/desktop-1..3.png`.

## Ownership model (per-user data scoping, P5b)

`sermons.user_id` / `background_jobs.user_id` (nullable TEXT, indexed).
`NULL` = unowned/legacy = admin-visible only. `role=user` callers see only
rows stamped with their id across list/search/sort/detail/plan/jobs
endpoints; foreign single-row fetches return 404, never 403. `role=admin`
sees everything.

Columns are added by a PRAGMA-checked `_ensure_columns` helper in
`server/api/accounts.py:migrate()` (the `CREATE TABLE IF NOT EXISTS` shape
never alters existing tables) and mirrored in `SermonDatabase.init_database`
+ `JobQueue._init_database` so Streamlit-managed databases gain them too.

One-time backfill (reassigns unowned rows to the first admin; safe to re-run;
historical sermons become admin-owned):

```bash
SERMONPILOT_DB=/data/sermon_processor.db .venv/bin/python -m server.api.backfill
```

Attribution: `JobQueue.add_job(..., user_id=...)` persists the owner without
clobbering on later status saves; `SermonRepository.save_sermon()` stamps
`user_id` from the payload only onto unowned rows; the sermon-processing and
apply executors (`ui/job_executors.py`) fill unowned sermon rows from the
job's `user_id` and never overwrite. The Streamlit path passes no `user_id`,
so its rows stay `NULL` (admin-visible). Job creation currently lives behind
UI code, so API-side creation wraps at the API layer when the write-path
increment lands.

New Sermon is not wired yet (read-only era): creation arrives with the
write-path increment, at which point `user_id` is stamped from the session.

## Roadmap: resumable/interruptible uploads (logged Sep 16, River)
Multiparty (chunked) uploads for the web console so large sermon files can be PAUSED and RESUMED across interruptions (browser restart, network drop, machine reboot). Server-side session keeps received chunk offsets; client resumes by querying state. Applies to Browser Upload path in New Sermon; Server Path ingest already handles huge files today. NOT started — design when the write-path phase lands.

## Roadmap: per-user cloud storage mounts (logged Sep 16, River)
Connect cloud storage (Google Drive, Dropbox, OneDrive, and S3-class all at v1 — including Backblaze B2) through the UI to a USER ACCOUNT: OAuth connect flow, files save to the user's mounted drive alongside SermonAudio upload. Builds on the existing host-side rclone Drive ingest design (W1-W5, v1.8.0) — that one is Tower-host-level (single mount, detect-and-notify); this is per-user in-app mounts at the accounts (P5) phase. NOT started.

## Roadmap: scripture overlay + audio disclaimer (logged Sep 16, River)
1. SCRIPTURE OVERLAY (automated): when the speaker reads Scripture, fade to a text card showing the exact passage being read (verse lookup via a Bible API — midvash-class or offline public-domain text), paged for long passages, then fade back to the speaker. Builds on existing transcript timestamps + logo-card overlay windows (xfade machinery in auto_edit). Needs: reading-segment detection (LLM + timestamps), verse matching (fuzzy match transcript text -> reference), text-card renderer, review-gate UI for proposed overlays.
2. AUDIO DISCLAIMER INTRO (optional per-sermon): optional pre-roll text card ('audio issues during recording...') rendered like the ending card — form option in New Sermon, persisted per sermon, rendered at render time.
NOT started — design at the write-path/render phase.

## P5f Files API scoping decision (Sep 17, River-approved default)
/api/me/files lists/downloads ONLY from the user's own configured output directory
(settings.general.output_dir, default processed_sermons). Path-traversal blocked
(resolve + prefix check, 400 on escape). Admin user management UI is admin-only
(role from /api/auth/me). Future hardening: per-sermon file scoping when per-user
output dirs fully land; until then the output dir IS the user boundary.

## Front-door cutover (P6c, prepared — NOT switched)

sermon.moraclan.us currently proxies to Streamlit :8501 via nginx (CT 111).
Cutover is a two-step manual operation:

1. River flips `web_console_ready: true` in the LIVE server config
   (`SA_UPDATER_CONFIG` file or `config.yaml`). The console reports it at
   `GET /api/meta/retirement` → `{"streamlit_ready": true}` (public, no auth),
   and Settings → System shows the state in a read-only admin-only banner.
2. Operator edits the nginx vhost `sermon.moraclan.us.conf`: move the upstream
   from `127.0.0.1:8501` (Streamlit) to `127.0.0.1:8504` (FastAPI bridge, which
   serves the console bundle + `/api/*`), then `nginx -t && nginx -s reload`.
   Keep these directives on the location block:
   - websocket headers (`proxy_http_version 1.1`, `Upgrade` + `Connection`
     maps) — the console polls over HTTP but future live tails use WS;
   - `proxy_buffering off` — streaming downloads (`/api/me/files/download`)
     and large multipart uploads must not spool;
   - `client_max_body_size 30G` — matches `SERMONPILOT_UPLOAD_GB` default 30.

Rollback: flip `web_console_ready` back to false and restore the 8501 upstream.
Nothing in this repo switches traffic on its own.
