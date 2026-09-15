# SermonPilot Console (web/)

Mock-first rebuild of the SermonPilot UI. The Streamlit app stays live; everything new lands here.

## Stack

React 18 + Vite 5 + TypeScript (strict) + Tailwind CSS 3 + shadcn-style local primitives (`src/components/ui.tsx`). No backend, no network calls in this phase. State-based routing, placeholder content only.

## Commands

```bash
cd web
npm install
npm run dev      # local preview
npm run build    # tsc --noEmit + vite build
npm run preview  # serve the build
```

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
