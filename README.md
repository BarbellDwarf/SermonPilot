# SermonPilot

Automated sermon processing tool that enhances audio (Clear/DeepFilterNet), transcribes (Whisper), generates AI metadata (title/description/hashtags via Ollama/OpenAI), and uploads to SermonAudio API. Provides a Streamlit web UI and CLI.

## Features

- **Audio Enhancement**: Clear (desert-ant-labs) ONNX model, built on DeepFilterNet 3, fine-tuned on speech corpus. Runs via ONNX Runtime with zero PyTorch dependency. Supports CUDA, ROCm, CPU. Falls back to DeepFilterNet.
- **Transcription**: Local Whisper/faster-whisper, OpenAI API, or OpenRouter
- **AI Metadata**: Title, description, and hashtag generation via Ollama, OpenAI, xAI, Groq, or OpenRouter
- **SermonAudio Integration**: Create, update, and upload sermons directly to SermonAudio API
- **Streamlit Web UI**: Dashboard, library, batch processing, validation, analytics, AI chat
- **Directory Structure**: `processed_sermons/{speaker}/{series}/{title} - {series} - {speaker}/`

## Quick Start

### Local Installation

```bash
git clone https://github.com/BarbellDwarf/SermonPilot.git
cd SermonPilot

# Install UV (fast package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install
uv venv --python 3.11
source .venv/bin/activate
uv sync

# Configure
cp .env.example .env
# Edit .env with your SermonAudio API key and broadcaster ID
```

No `config.yaml` is needed. On first launch the environment variables are
seeded into the SQLite settings database; see [Configuration](#configuration).

### Docker (Pre-built Images)

Pre-built images are available on GitHub Container Registry. Choose your GPU backend:

```bash
# Configure first: copy the environment template and fill in your API keys
cp .env.example .env

# Pull and run with CPU
SERMONPILOT_TAG=cpu docker compose up -d

# Or pin a specific version and backend
SERMONPILOT_TAG=v1.6.2-cuda docker compose up -d
```

Images are tagged as `ghcr.io/barbelldwarf/sermonpilot:TAG-BACKEND` (e.g. `v1.6.2-cuda`, `v1.6.2-rocm`, `v1.6.2-cpu`). Moving per-backend tags (`cuda`, `rocm`, `cpu`) track the latest release of each backend, and `latest` points to the latest CUDA build.

### Hardware Acceleration

To use GPU acceleration, you need to:

1. **Pull the correct image tag**: set `SERMONPILOT_TAG` to a version with your backend (e.g. `v1.6.2-cuda`)

2. **Add device access to docker-compose.yml**: uncomment or add the appropriate `deploy` section:

   **NVIDIA CUDA:**
   ```yaml
   services:
     sermon-pilot:
       image: ghcr.io/barbelldwarf/sermonpilot:${SERMONPILOT_TAG:-latest}
       # ... other config ...
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: all
                 capabilities: [gpu]
   ```

   **AMD ROCm:**
   ```yaml
   services:
     sermon-pilot:
       image: ghcr.io/barbelldwarf/sermonpilot:${SERMONPILOT_TAG:-latest}
       # ... other config ...
       devices:
         - /dev/kfd
         - /dev/dri
   ```

3. **Install the container toolkit** if you haven't already:
   - **NVIDIA**: [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
   - **AMD**: [rocm-docker](https://rocm.docs.amd.com/en/latest/deploy/docker.html)

   On AMD GPUs, `whisper_local` (openai-whisper, torch-based) runs on the GPU;
   `faster_whisper_local` uses CTranslate2, which has no ROCm support and is
   forced to CPU. The `rocm` image ships a matching config template
   (`config/templates/rocm.yaml`) that selects `whisper_local` and is offered
   for import at startup. See [docs/GPU_INSTALLATION.md](docs/GPU_INSTALLATION.md).

### Build Locally

```bash
docker build -t sermonpilot:latest .
# Or with GPU support:
docker build --build-arg GPU_BACKEND=cuda -t sermonpilot:latest .
```

> **Ollama**: If using Ollama for local LLM inference, run it separately:
> `docker run -d --name ollama -p 11434:11434 ollama/ollama`
> Then set `OLLAMA_HOST=http://host.docker.internal:11434` in your `.env`.

## Configuration

Settings live in a SQLite settings database and are resolved in this order,
lowest to highest: built-in defaults, an optional file layer (`SA_UPDATER_CONFIG`),
the settings database, then environment variables (env always wins for the
running process). There is no required config file.

```bash
cp .env.example .env
```

Environment variables that seed and override settings:

| Area | Variables |
|------|-----------|
| SermonAudio | `SERMONAUDIO_API_KEY`, `SERMONAUDIO_BROADCASTER_ID` |
| LLM provider | `LLM_PROVIDER`, `OLLAMA_HOST`, `OLLAMA_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `XAI_API_KEY`, `XAI_MODEL`, `GROQ_API_KEY`, `GROQ_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `GOOGLE_API_KEY`, `GOOGLE_MODEL` |
| Transcription | `TRANSCRIPTION_BACKEND`, `WHISPER_MODEL` |
| Audio | `AUDIO_ENHANCEMENT_METHOD`, `AUDIO_NOISE_REDUCTION`, `AUDIO_NORMALIZE`, `AUDIO_TARGET_LEVEL`, `AUDIO_GAIN_DB`, `QA_NORMALIZATION_ENABLED` |
| Output | `OUTPUT_DIRECTORY`, `SAVE_TRANSCRIPT`, `SAVE_ORIGINAL_AUDIO` |
| Embeddings | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` |
| Behavior | `DEBUG`, `VERBOSE`, `DRY_RUN`, `HASHTAG_VERIFICATION` |
| Runtime (not part of the settings store) | `DATABASE_URL`, `APP_PASSWORD` |

On first launch with any of these set, the resolved values are written into the
settings database once, so a container started with only a `.env` file keeps
its settings across restarts. Change settings any time in the web UI Settings
page; environment variables still override the stored values per process.

`config.yaml` is export/import only and never read for resolution:

- On an existing install that still has a `config.yaml`, its contents are
  imported into the settings database once, automatically.
- The Settings page has an Import/Export tab that downloads the current
  settings as YAML and restores from an uploaded YAML file.
- Set `SA_UPDATER_CONFIG` to a YAML path to load it as an extra layer between
  defaults and the database (escape hatch for tests and unusual setups).
- Docker images ship per-variant templates under `config/templates/`
  (`cuda.yaml`, `rocm.yaml`, `cpu.yaml`) that differ in the transcription
  section; the container startup logs the matching template for your image.

Commonly tuned keys (set them in the UI, in the file layer, or via the env
vars above):

- `audio_enhancement_method`: `deepfilternet` (default, recommended), `clear-natural`, `clear-studio`, `custom`, or `none`
- `transcription.backend`: `whisper_local` (code default), `faster_whisper_local`, `whisper_openai`, or `whisper_openrouter`
- `upload_dir`: staging directory for files uploaded through the web UI; defaults to `sermon_uploads` under the disk-backed cache root (`$XDG_CACHE_HOME/sermonpilot` or `~/.cache/sermonpilot`)
- `processing_temp_dir`: parent directory for per-job processing temp dirs; defaults to `sermon_processing` under the same cache root. Each job gets its own subdirectory, removed when the job ends; leftovers older than 24h are swept at startup

## Usage

### Web Interface
```bash
streamlit run streamlit_app.py
# Open http://localhost:8501
```

#### Filename auto-detection

When you upload a file on the **New Sermon** page, SermonPilot reads the filename and pre-fills the metadata form. Name your recordings:

```
Title - Series - Speaker - date.extension
```

Segments are positional, split on the literal `" - "` separator, and anything past the fourth segment is ignored.

| Position | Segment | Fills | If missing |
|----------|---------|-------|------------|
| 1 | Title | Sermon Title | Left blank for AI generation |
| 2 | Series | Series dropdown (selects an existing series, otherwise pre-fills "Add New") | Left empty |
| 3 | Speaker | Speaker dropdown (selects an existing pastor, otherwise pre-fills "Add New") | Left empty |
| 4 | Date | Recording Date; accepts `YYYY-MM-DD`, `YYYY_MM_DD`, `MM-DD-YYYY`, `MM_DD_YYYY`, `DD.MM.YYYY` | Stays at today's default |

Detection runs once per uploaded filename and only fills fields still at their defaults, so your own edits are never overwritten.

Examples:
- `My Sermon - Romans - Paul - 2026-08-20.mp4` fills title "My Sermon", series "Romans", speaker "Paul" and date 2026-08-20
- `Evening Prayer.mp4` fills only the title "Evening Prayer"

### CLI - New Sermon
```bash
python sermon_updater.py new-sermon audio.mp3 --speaker "Pastor Smith" --date "2024-01-15"
```

### CLI - Process Existing
```bash
python sermon_updater.py sermon-update --sermon-id 1234567890123
```

### CLI - List Sermons
```bash
python sermon_updater.py list --since-days 30
```

## Audio Enhancement

| Method | Description | Torch Dep | GPU Support |
|--------|-------------|-----------|-------------|
| **DeepFilterNet** (default) | Original DFN3 PyTorch model | Required | CUDA/ROCm |
| Clear | ONNX model (desert-ant-labs/clear), DFN3 architecture, fine-tuned speech corpus (`clear-natural`/`clear-studio`) | None | CUDA/ROCm/CPU via ONNX Runtime |
| none | No enhancement | None | n/a |

## Directory Structure

```
processed_sermons/
|-- Speaker Name/
|   |-- Series Name/
|   |   `-- Sermon Title - Series Name - Speaker Name/
|   |       |-- audio.mp3
|   |       |-- transcript.txt
|   |       |-- description.txt
|   |       |-- hashtags.txt
|   |       `-- metadata.json
|   `-- Another Series/
|       `-- Another Sermon - Another Series - Speaker Name/
`-- Another Speaker/
    `-- A Series/
        `-- A Sermon - A Series - Another Speaker/
```

## Security

- **PyTorch** is pinned at `torch>=2.6.0` in `pyproject.toml`; the GPU override files resolve CUDA (`torch==2.6.0+cu124`) or ROCm (`torch==2.12.1+rocm7.1`) builds
- **Clear enhancer** uses ONNX Runtime: zero PyTorch dependency for inference
- API keys stored in `.env` (gitignored) or as environment variables
- Secrets never need to touch disk in plaintext: keep them in the environment or as `${VAR}` placeholders in an imported file layer; the Settings export masks them

## License

MIT
