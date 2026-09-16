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

## Roadmap: resumable/interruptible uploads (logged Sep 16, the operator)
Multiparty (chunked) uploads for the web console so large sermon files can be PAUSED and RESUMED across interruptions (browser restart, network drop, machine reboot). Server-side session keeps received chunk offsets; client resumes by querying state. Applies to Browser Upload path in New Sermon; Server Path ingest already handles huge files today. NOT started — design when the write-path phase lands.

## Roadmap: per-user cloud storage mounts (logged Sep 16, the operator)
Connect cloud storage (Google Drive, Dropbox, OneDrive, and S3-class all at v1 — including Backblaze B2) through the UI to a USER ACCOUNT: OAuth connect flow, files save to the user's mounted drive alongside SermonAudio upload. Builds on the existing host-side rclone Drive ingest design (W1-W5, v1.8.0) — that one is Tower-host-level (single mount, detect-and-notify); this is per-user in-app mounts at the accounts (P5) phase. NOT started.
