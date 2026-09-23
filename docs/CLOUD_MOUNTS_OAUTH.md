# Cloud mount OAuth: bring your own Google client ID

Cloud mounts (**Settings → Cloud Mounts**) connect to Google Drive (and other
providers) through `rclone`, configured per user on the server. Google Drive
mounts currently authenticate with **rclone's shared client ID**, which Google
retires for third parties during 2026. Every deployment that mounts Drive needs
its own client ID before that happens, or the mounts stop authenticating.

This is an operator task, done once per deployment — no command line required.

## What you need

- A Google Cloud project (the free tier is enough)
- The **Google Drive API** enabled in it
- An OAuth client of type **Desktop app** (its *client ID* and *client secret*)

## Steps

1. **Create the OAuth client** — Google Cloud console → *APIs & Services* →
   *Credentials* → *Create credentials* → *OAuth client ID* → *Desktop app*.
   Copy the client ID and client secret.
2. **Enter them in the app** — *Settings → Cloud Mounts → Advanced* ("use your
   own OAuth client"). The secret is stored server-side and is never displayed
   again; the client ID stays visible so you can confirm which one is in use.
3. **Re-authorize the remotes** — a token issued to the shared client is not
   valid for yours. For each existing remote: *Cloud Mounts → remote → Connect*
   (or *Re-authorize*), complete the Google consent screen, and paste the
   returned URL back when the app asks for it.
4. **Verify** — open the remote in *Cloud Mounts* and list a folder. If the
   browse works, the mount is live; the same check runs at upload time.

## Notes

- Remotes keep working until Google retires the shared client. Doing this early
  is a no-risk change: it only affects future token refreshes.
- Each user's remotes are stored separately (`rclone` config per user, mode
  `0600`); one user's client ID does not affect another's remotes.
- If a mount is created *without* a client ID after the shared one retires, the
  connect step fails with an OAuth error naming the client — set the client ID
  first, then retry.

## What the app does for you

- Stores the client ID and secret server-side (never echoed back to the browser).
- Reports the mount's state (`connected` / `needs re-authorization`) in Cloud
  Mounts, so a stale token is visible before an upload depends on it.
- Uses the same client ID for every operation on that remote: browse, stage,
  write back, and the ingest watcher when it is enabled.
