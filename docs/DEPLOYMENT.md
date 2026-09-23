# Deployment

This guide covers running SermonPilot from the published container image with
Docker Compose. Builds happen in CI; the deployment host pulls the image.
Configuration is environment variables plus the SQLite database, and the database
is authoritative for connections once it is seeded.

## The image

Images are published to GitHub Container Registry:

```
ghcr.io/barbelldwarf/sermonpilot
```

Release tags carry a backend suffix: `vX.Y.Z-cuda`, `vX.Y.Z-rocm`, `vX.Y.Z-cpu`.
The moving per-backend tags (`cuda`, `rocm`, `cpu`) track the latest release of
each backend, and `latest` points at the latest CUDA build. Pick the backend that
matches the host GPU.

Pull the image (optional, `docker compose up` pulls it when it is missing):

```bash
SERMONPILOT_TAG=cuda docker compose pull sermon-pilot
```

## The compose service

`docker-compose.yml` at the repository root defines one service, `sermon-pilot`.
It pulls `ghcr.io/barbelldwarf/sermonpilot:${SERMONPILOT_TAG:-latest}`, restarts
unless stopped, and reads `.env` when present.

The console, which is the API server plus the built React bundle, listens on
**8504**. The legacy Streamlit interface listens on **8501**. Both run inside the
one container.

The checked-in compose file publishes only 8501, so a plain
`docker compose up -d` exposes the legacy UI. To reach the console, add the 8504
mapping to the service before starting:

```yaml
ports:
  - "${HOST_BIND:-127.0.0.1}:8501:8501"   # legacy Streamlit UI
  - "${HOST_BIND:-127.0.0.1}:8504:8504"   # API + web console
```

`HOST_BIND` defaults to `127.0.0.1`, which keeps both ports on the host. Set
`HOST_BIND=0.0.0.0` to expose them on the network, and set the console admin
credentials first. A reverse proxy in front of either port is the operator's
choice; the API reads `X-Forwarded-Proto` and `X-Forwarded-Host` and is happy
behind one.

## Required environment variables

Put these in `.env` next to `docker-compose.yml`, which compose loads
automatically, or export them wherever the container is started. Replace every
placeholder.

| Variable | Purpose | Example |
|---|---|---|
| `SERMONPILOT_ADMIN_USER` | Console admin username created on first boot | `admin` |
| `SERMONPILOT_ADMIN_PASSWORD` | Console admin password created on first boot | `<a-strong-password>` |
| `SERMONAUDIO_API_KEY` | SermonAudio API key, seeded into the database | `<your-api-key>` |
| `SERMONAUDIO_BROADCASTER_ID` | SermonAudio broadcaster id, seeded into the database | `<your-broadcaster-id>` |
| `DATABASE_URL` | SQLite location | `sqlite:///data/sermon_processor.db` |
| `SERMONPILOT_TAG` | Image backend or tag to pull | `cuda` |
| `HOST_BIND` | Bind address for the published ports | `127.0.0.1` |
| `APP_PASSWORD` | Password for the legacy Streamlit UI | `<a-strong-password>` |
| `OLLAMA_HOST` | Ollama endpoint when using a local model | `http://host.docker.internal:11434` |

The console creates its admin account from `SERMONPILOT_ADMIN_USER` and
`SERMONPILOT_ADMIN_PASSWORD` on the first bootstrap. After that, accounts live in
the database and admins manage them in Settings. `APP_PASSWORD` gates only the
legacy Streamlit UI.

SermonAudio credentials are seeded into the database on first launch and edited
afterwards in **Settings -> SermonAudio Accounts**, with the single-account
fallback below that list. An exported `SERMONAUDIO_API_KEY` or
`SERMONAUDIO_BROADCASTER_ID` still wins while it is set, and the Settings page
names the environment variable that is winning.

Provider API keys (`OPENAI_API_KEY`, `XAI_API_KEY`, `GROQ_API_KEY`,
`OPENROUTER_API_KEY`) and the model pins are deploy-time secrets. They stay in
the environment, are never copied into the database, and override the stored
value while set.

## Volumes

The compose file declares named volumes. The two that matter for a deployment are
the database and the processed media:

| Volume | Container path | Holds |
|---|---|---|
| `sermon_data` | `/data` | SQLite database, uploads, branding |
| `sermon_output` | `/app/processed_sermons` | Processed sermons and rendered edits |

The remaining volumes (`sermon_models`, `sermon_api_cache`, `sermon_cache`,
`sermon_logs`) cache models and API responses and hold logs. Compose prefixes
volume names with the project name, so they appear as `<project>_sermon_data`.
Back up `sermon_data` to keep the database, and `sermon_output` to keep the
processed media.

## Deploy sequence

From the directory holding `docker-compose.yml` and `.env`:

1. Pull the image:

   ```bash
   SERMONPILOT_TAG=cuda docker compose pull sermon-pilot
   ```

2. Recreate the container on the new image:

   ```bash
   SERMONPILOT_TAG=cuda docker compose up -d
   ```

3. Confirm the process came up and the database initialized:

   ```bash
   docker compose logs --tail 50 sermon-pilot
   ```

   Look for `Database ready`, the `Variant:` line, and the `GPU:` and
   `ORT providers:` lines on a GPU image.

4. Confirm health. The health endpoint is public and reports the running version
   and whether the database is readable:

   ```bash
   curl -fsS http://127.0.0.1:8504/api/health
   ```

   Expected: `{"ok":true,"version":"...","db_path_ok":true}`.

   The checked-in compose file disables the container healthcheck
   (`test: ["NONE"]`), so this request is the health check.

5. Confirm the console loads:

   ```bash
   curl -fsS http://127.0.0.1:8504/ | head
   ```

   Then open `http://<your-host>:8504/` in a browser. The sign-in screen is the
   confirmation that the bundle and the API are both being served.

## Model and LLM configuration

Configure the provider and model in **Settings -> LLM Providers**. There are
three slots:

- **Primary** generates metadata and runs by default.
- **Fallback** catches failures when the primary cannot answer.
- **Validator** reviews drafts before they reach SermonAudio.

Each slot takes a provider (Ollama, OpenAI-compatible, xAI, Groq, or
OpenRouter), an endpoint, a model id, an optional API key, and optional
generation settings. A **Test connection** button runs a fixed one-word prompt
against the saved configuration and reports the measured latency. Routing, which
slot handles metadata generation, validation, transcription assist, and fallback,
is set just below the slots.

A local Ollama server is the zero-key option: set `OLLAMA_HOST`, then point the
Ollama slot at it. A hosted provider needs its API key. Environment variables
remain the fallback layer, so `LLM_PROVIDER`, `OLLAMA_HOST`, `OLLAMA_MODEL`, and
the per-provider `*_API_KEY` and `*_MODEL` variables override the stored value
for the running process.

## Verify a deployment end to end

1. **Health**: `curl -fsS http://127.0.0.1:8504/api/health` returns `ok: true`
   and `db_path_ok: true`.
2. **Sign in**: open the console and sign in with the bootstrap admin account.
   **Settings -> LLM Providers** should load, and **Test connection** on the
   primary slot should pass.
3. **One dry run on a short clip**: in **New Sermon**, pick a short recording (a
   few minutes), fill in title, speaker, and date, turn on **Dry run**, and start
   it. Watch it under **Jobs**. A dry run processes locally and skips the
   SermonAudio upload, so it exercises the pipeline without publishing anything.
   When it finishes, the sermon is in **Library** as a draft.

## Ports

| Port | Serves |
|---|---|
| `8504` | API server and web console (`SERMONPILOT_WEB_PORT` overrides it) |
| `8501` | Legacy Streamlit UI (`STREAMLIT_SERVER_MAX_UPLOAD_SIZE` sets its upload cap) |

Both are plain HTTP inside the container. Terminating TLS and choosing a hostname
is the operator's job; the API is built to sit behind a reverse proxy.

## Troubleshooting

**The container is up but the console is blank.**
The API serves the built bundle from `web/dist` inside the image, so a blank page
usually means the bundle is missing or stale. Check that the image carries the
assets:

```bash
docker compose exec sermon-pilot ls /app/web/dist
```

You should see `index.html` and an `assets/` directory. When they are there,
reload with the browser cache disabled, since an old bundle can be cached across
a redeploy. Check the API logs for errors too:

```bash
docker compose logs --tail 100 sermon-pilot
```

**The queue is stuck.**
Cancel the job from **Jobs** (Cancel on the job row). After a container recreate,
startup reconciliation marks jobs that were left `running` by the dead worker as
failed with a `Job interrupted by app restart` line, so a stuck row clears on its
own. The console's Retry button reports that retry is unavailable in the
read-only bridge, so to run the work again, start it from the sermon: approve the
cut again on the review page, or queue the sermon again from **New Sermon**.

**An upload fails.**
Check **Settings -> SermonAudio Accounts**: the selected account, or the default,
needs a valid API key and broadcaster id, and the key's last four characters
should match what you expect. The single-account fallback below the accounts list
is used when no account is picked. The upload job's log under **Jobs** carries
the API's error message. A broadcaster id that does not match the API key's
account is a common cause.
