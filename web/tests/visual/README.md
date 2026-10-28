# Visual regression baselines

Playwright captures Home, Library, Jobs, Settings, New teaching, and Review at
390x844 and 1440x900, in dark and light themes. Screenshots live in
`__screenshots__/<project>/` and are committed, so a UI change shows up as a
diff instead of silent drift.

The suite runs against the built demo bundle (`npm run build` then
`vite preview`), with a pinned clock so relative timestamps stay stable.

## Run

```bash
cd web
npm run visual
```

## Update after an intentional UI change

```bash
cd web
npm run visual:update
```

Review the changed images in `tests/visual/__screenshots__/` before committing
them. Failures leave `test-results/` with actual and diff images.

## Notes

- The app must be in demo mode (no `VITE_API_MODE=live`). `vite preview` serves
  the last build, and `npm run visual` rebuilds first.
- A failure means either the change was unintended, or the baseline is stale.
  Update only after looking at the diff.
