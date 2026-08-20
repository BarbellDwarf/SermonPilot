# Docker Guide

This guide covers running SermonPilot with Docker: pulling prebuilt images,
running the single-service stack from `docker-compose.yml`, building images
locally, and enabling GPU acceleration.

## What the stack contains

The compose file defines one service, `sermon-pilot`, which runs the
Streamlit web UI on port 8501. There is no separate API server, Redis,
PostgreSQL, or Ollama container in the stack. Ollama, when used, runs
outside the container and is reached through `OLLAMA_HOST`.

The container entrypoint is `docker/start_production.sh`, which:

1. Creates the persistent data directories (`/data`, `/app/processed_sermons`, `/app/logs`)
2. Waits for external services via `docker/wait_for_services.py` when `DATABASE_HOST` is set
3. Initializes the SQLite database through `SermonRepository`
4. Starts `streamlit run streamlit_app.py` on `0.0.0.0:8501`

## Prerequisites

- Docker with the Compose plugin (`docker compose version`)
- For GPU support: the NVIDIA Container Toolkit or the ROCm Docker setup

## Quick start

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at least:

- `SERMONAUDIO_API_KEY`
- `SERMONAUDIO_BROADCASTER_ID`
- `APP_PASSWORD` (recommended; the app binds to `127.0.0.1` by default, set `HOST_BIND=0.0.0.0` only when a password is set)

LLM provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`) are
optional. For local inference, set `OLLAMA_HOST` to a running Ollama server;
the compose default is `http://host.docker.internal:11434`, which reaches an
Ollama container or host process on the Docker host.

### 2. Start the stack

```bash
docker compose up -d
```

Wait for the health check to pass, then open http://localhost:8501.

```bash
docker compose ps
```

### 3. Verify it works

```bash
curl http://localhost:8501/
docker compose logs -f sermon-pilot
```

## Images

Prebuilt images are published to GitHub Container Registry as
`ghcr.io/barbelldwarf/sermonpilot`. Release tags carry a backend suffix:
`v1.5.3-cuda`, `v1.5.3-rocm`, `v1.5.3-cpu`. The `latest` tag points at the
latest CUDA build.

Pin a backend with the `SERMONPILOT_TAG` variable:

```bash
SERMONPILOT_TAG=v1.5.3-cuda docker compose up -d
```

## GPU support

### NVIDIA CUDA

1. Install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).
2. Add device access to `docker-compose.yml`:

```yaml
services:
  sermon-pilot:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

3. Use a CUDA image tag: `SERMONPILOT_TAG=v1.5.3-cuda docker compose up -d`.

Check GPU access inside the container:

```bash
docker compose exec sermon-pilot nvidia-smi
```

### AMD ROCm

1. Set up [ROCm Docker](https://rocm.docs.amd.com/en/latest/deploy/docker.html).
2. Add device access to `docker-compose.yml`:

```yaml
services:
  sermon-pilot:
    devices:
      - /dev/kfd
      - /dev/dri
```

3. Use a ROCm image tag: `SERMONPILOT_TAG=v1.5.3-rocm docker compose up -d`.

## Building locally

```bash
docker build -t sermonpilot:latest .
```

Pick a GPU backend with the `GPU_BACKEND` build argument (`cpu`, `cuda`, or
`rocm`; `cpu` is the default):

```bash
docker build --build-arg GPU_BACKEND=cuda -t sermonpilot:latest .
docker build --build-arg GPU_BACKEND=rocm -t sermonpilot:latest .
```

The `cuda` backend installs `onnxruntime-gpu` in addition to the base
requirements; the `rocm` backend installs `requirements/requirements-rocm.txt`.

## Volumes

The compose file declares these named volumes and mounts them into the
container:

| Volume | Container path | Purpose |
|--------|----------------|---------|
| `sermon_data` | `/data` | SQLite database and app data |
| `sermon_models` | `/models` | Downloaded AI model cache |
| `sermon_api_cache` | `/app/api_cache` | API response cache |
| `sermon_output` | `/app/processed_sermons` | Processed sermon output |
| `sermon_cache` | `/home/sermonapp/.cache` | User-level cache (Hugging Face, torch) |
| `sermon_logs` | `/app/logs` | Application logs |

Compose prefixes the volume names with the project name (the compose file's
directory name), so they appear as `<project>_sermon_data` in `docker volume ls`.

## Backups

The `docker/backup/` directory contains `backup_script.sh` and
`restore_script.sh`. Both scripts reference a container named
`sermon-processor` and an optional `sermon-postgres` container. The current
compose file names the service `sermon-pilot`, so update the
`CONTAINER_NAME` variable in both scripts before using them.

A manual backup of the app data volume works without the scripts:

```bash
docker run --rm --volumes-from sermon-pilot -v "$PWD":/backup \
  alpine tar czf /backup/sermon_data_backup.tar.gz /data
```

Restore with:

```bash
docker run --rm --volumes-from sermon-pilot -v "$PWD":/backup \
  alpine sh -c "cd / && tar xzf /backup/sermon_data_backup.tar.gz"
```

## Common commands

```bash
# Build all images
docker compose build

# Start services
docker compose up -d

# Follow logs
docker compose logs -f sermon-pilot

# Open a shell in the container
docker compose exec sermon-pilot bash

# Stop services
docker compose down

# Remove containers and named volumes
docker compose down -v
```

The image excludes `tests/` and `docs/` via `.dockerignore`, so there is no
pytest or test suite inside the container. Run tests from a local checkout.

## Troubleshooting

**The UI is not reachable.** Check `docker compose ps` and the logs with
`docker compose logs sermon-pilot`. The health check is
`curl -f http://localhost:8501/`, and Streamlit needs a few seconds to start.

**Port 8501 is already in use.** Change the published port in
`docker-compose.yml`, for example `"127.0.0.1:8502:8501"`.

**The app is only reachable from localhost.** `HOST_BIND` defaults to
`127.0.0.1`. Set `HOST_BIND=0.0.0.0` in `.env` to expose the UI on the
network, and keep `APP_PASSWORD` set.

**Ollama is not reachable.** From the host, check the Ollama server:

```bash
curl http://localhost:11434/api/tags
```

Inside the container, `OLLAMA_HOST` must point at a reachable address. For an
Ollama container on the same Docker host, `http://host.docker.internal:11434`
works on Docker Desktop and recent Docker Engine releases.

**GPU not detected.** Verify the toolkit is installed, the `deploy` or
`devices` section is present in `docker-compose.yml`, and you are running an
image built for your backend (`cuda` or `rocm` tag). Then check
`docker compose exec sermon-pilot nvidia-smi`.

**Volume permissions.** The container runs as user `sermonapp` (UID 1000).
If a bind-mounted host directory is not writable by that UID, adjust the
host directory ownership or permissions.
