# SermonPilot

Automated sermon processing tool that enhances audio (Clear/DeepFilterNet), transcribes (Whisper), generates AI metadata (title/description/hashtags via Ollama/OpenAI), and uploads to SermonAudio API. Provides a Streamlit web UI and CLI.

## Features

- **Audio Enhancement**: Clear (desert-ant-labs) ONNX model — built on DeepFilterNet 3, fine-tuned on speech corpus. Runs via ONNX Runtime with zero PyTorch dependency. Supports CUDA, ROCm, CPU. Falls back to DeepFilterNet or noisereduce.
- **Transcription**: Local Whisper/faster-whisper, OpenAI API, or OpenRouter
- **AI Metadata**: Title, description, and hashtag generation via Ollama, OpenAI, Anthropic, xAI, or Google
- **SermonAudio Integration**: Create, update, and upload sermons directly to SermonAudio API
- **Streamlit Web UI**: Dashboard, library, batch processing, validation, analytics, AI chat
- **Directory Structure**: `processed_sermons/{speaker}/{series}/{title} - {series} - {speaker}/`

## Quick Start

### Local Installation

```bash
git clone <repository-url>
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

### Docker (Pre-built Images)

Pre-built images are available on GitHub Container Registry. Choose your GPU backend:

```bash
# Pull and run with CPU
docker compose up -d

# Or pin a specific version
SERMONPILOT_TAG=v1.5.0 docker compose up -d
```

Images are tagged as `ghcr.io/barbelldwarf/sermonpilot:TAG-BACKEND` (e.g. `v1.5.0-cuda`, `v1.5.0-rocm`, `v1.5.0-cpu`). The `latest` tag points to the latest CUDA build.

### Hardware Acceleration

To use GPU acceleration, you need to:

1. **Pull the correct image tag** — set `SERMONPILOT_TAG` to a version with your backend (e.g. `v1.5.1-cuda`)

2. **Add device access to docker-compose.yml** — uncomment or add the appropriate `deploy` section:

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

Copy `.env.example` to `.env` and fill in your values:

```bash
SERMONAUDIO_API_KEY=your-api-key
SERMONAUDIO_BROADCASTER_ID=your-broadcaster-id
OLLAMA_HOST=http://localhost:11434
```

Key `config.yaml` settings:
- `audio_enhancement_method`: `deepfilternet` (default, recommended), `clear`, or `none`
- `transcription.backend`: `whisper_local`, `whisper_openai`, or `whisper_openrouter`

## Usage

### Web Interface
```bash
streamlit run streamlit_app.py
# Open http://localhost:8501
```

### CLI — New Sermon
```bash
python sermon_updater.py new-sermon audio.mp3 --speaker "Pastor Smith" --date "2024-01-15"
```

### CLI — Process Existing
```bash
python sermon_updater.py sermon-update --sermon-id 1234567890123
```

### CLI — List Sermons
```bash
python sermon_updater.py list --since-days 30
```

## Audio Enhancement

| Method | Description | Torch Dep | GPU Support |
|--------|-------------|-----------|-------------|
| **Clear** (default) | ONNX model, DFN3 architecture, fine-tuned speech corpus | None | CUDA/ROCm/CPU via ONNX Runtime |
| DeepFilterNet | Original DFN3 PyTorch model | Required | CUDA/ROCm |
| Resemble Enhance | Denoising + enhancement | Required | CUDA |
| noisereduce | Spectral gating (lightweight) | None | CPU only |

## Directory Structure

```
processed_sermons/
├── Speaker Name/
│   ├── Series Name/
│   │   └── Sermon Title - Series Name - Speaker Name/
│   │       ├── audio.mp3
│   │       ├── transcript.txt
│   │       ├── description.txt
│   │       ├── hashtags.txt
│   │       └── metadata.json
│   └── Another Series/
│       └── Another Sermon - Another Series - Speaker Name/
└── Another Speaker/
    └── A Series/
        └── A Sermon - A Series - Another Speaker/
```

## Security

- **torch 2.12.1** (latest) — all 54 CVEs fixed including 4 critical
- **Clear enhancer** uses ONNX Runtime — zero PyTorch dependency for inference
- API keys stored in `.env` (gitignored) or as environment variables
- `config.yaml` uses `${VAR}` env var substitution — no secrets in repo

## License

MIT
