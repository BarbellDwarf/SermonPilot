# SermonPilot

SermonPilot takes a raw service recording and turns it into a finished sermon: it
cleans and enhances the audio, transcribes it, finds and trims the dead time, and
renders the edited video with an ending card. It publishes the result to
SermonAudio with an AI-drafted title, description, and hashtags. All of it is
operated from a web console.

## What the console does

- **Three ways to add a recording**: upload a file in the browser, point at a
  path on the server, or pick a file from a configured cloud mount.
- **Cloud mounts without a command line**: connect Google Drive, Dropbox,
  OneDrive, an S3-compatible bucket, or Backblaze B2 in Settings -> Cloud Mounts,
  browse the remote, and use a file straight from the picker.
- **One player, one timeline**: the review page shows a single player and a
  single timeline with markers for the keep region, the opening and closing cuts,
  and the ending card. Adjust the cut points, preview each segment, then approve.
- **Approve and publish**: approving a cut renders the edited video with the
  ending card, and the same action can upload it to SermonAudio. A render-only
  approve saves locally and can be published later with "Upload existing render".
- **A background job queue**: every run appears under Jobs with live status and
  per-job logs. A queued or running job can be cancelled.
- **Recoverable deletion**: deleting a sermon moves local media into a dated
  trash area, and cloud media stays on its remote.
- **Finished sermons stay editable**: a published sermon shows its details and
  can be re-opened to re-render or edit.

The legacy Streamlit interface (`ui/`) is still present and is served on its own
port while the console takes over.

## Quick start

The console runs in a browser. There is no command line for the operator.

1. Open the console URL for your deployment.
2. Sign in. On a fresh deployment the first admin account is bootstrapped from
   the environment (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)); after that,
   admins create accounts in Settings.
3. Go to **New Sermon**. Pick one source: upload a file, enter a server path, or
   choose a cloud file. Cloud remotes are connected under
   **Settings -> Cloud Mounts**.
4. Fill in title, speaker, and date (the rest is optional), choose the processing
   options, and start the run. A dry run processes locally and skips the
   SermonAudio upload.
5. Open the sermon in **Library** to review the proposed cuts, then approve.
   Follow the run under **Jobs**.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the image, environment,
volumes, and first boot.

## Documentation

The full docs index is [docs/](docs/). Start with
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) to deploy,
[docs/AUTO_EDIT.md](docs/AUTO_EDIT.md) for cut detection and the review workflow,
and [docs/CLOUD_MOUNTS_OAUTH.md](docs/CLOUD_MOUNTS_OAUTH.md) for the cloud mount
OAuth client.

## Architecture

- **Console** (`web/`): React, Vite, TypeScript, Tailwind. Talks to the API over
  JSON.
- **API server** (`server/api/`): FastAPI. Serves the console bundle and the
  `/api/*` routes, reads the SQLite database, and queues jobs. Account sessions
  gate every route except health, login, bootstrap, the cutover metadata, and the
  OAuth callback.
- **Job queue** (`ui/job_queue.py`, `ui/job_executors.py`): jobs run in a
  background queue, serialized by default, with cancel and per-job logs.
- **Media pipeline** (`sermon_updater.py`, `src/`): clean, enhance, mux,
  transcribe, detect cuts, render the approved edit with the ending card, upload.
- **LLM roles**: a primary provider generates metadata, a fallback catches
  failures, and a validator reviews drafts. Each role has its own provider,
  model, and endpoint in **Settings -> LLM Providers**.

Configuration lives in the SQLite database and is managed in Settings.
Environment variables are a visible fallback: a mapped variable overrides the
stored value for the running process, and the Settings UI names the variable that
is winning.

## Requirements

- Docker with the Compose plugin.
- A GPU host is recommended for the media work (audio enhancement, transcription,
  and the render). The CPU image works, more slowly.
- ffmpeg is included in the container image. Nothing beyond Docker is needed on
  the host.
- A reachable LLM provider: a local Ollama endpoint or a hosted provider
  (OpenAI-compatible, xAI, Groq, OpenRouter).

## License

MIT
