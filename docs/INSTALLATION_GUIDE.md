# Installation Guide

This guide covers installing SermonPilot from source. `pyproject.toml` is the
single source of truth for dependencies; `requirements/` provides derived
files for specific hardware scenarios. Choose the file that matches your
hardware and performance needs.

## Prerequisites

- Python **3.10+** (see `requires-python = ">=3.10"` in `pyproject.toml`)
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- ffmpeg/ffprobe for audio duration detection and video muxing
- 4 GB+ RAM (8 GB+ recommended for GPU transcription)

## Available Requirements Files

| File | Use case |
|------|----------|
| `requirements/requirements.txt` | Default: base runtime dependencies (torch family at the manifest floor) |
| `requirements/requirements-cpu.txt` | CPU-only PyTorch builds (CPU index) |
| `requirements/requirements-gpu.txt` | NVIDIA CUDA builds (cu124 index) |
| `requirements/requirements-rocm.txt` | AMD ROCm builds (rocm7.1 index) |
| `requirements/requirements-linux.txt` | Linux convenience install (CUDA index) |
| `requirements/requirements-dev.txt` | Development and testing tools |
| `requirements/requirements-models-deepfilternet.txt` | DeepFilterNet model extras |
| `requirements/requirements-models-all.txt` | All AI enhancement models combined |

The torch family is pinned once in `pyproject.toml` (`torch>=2.6.0`,
`torchaudio>=2.6.0`). Each override file adds the matching wheelhouse index
and pins the same version with the platform suffix, so any install satisfies
the manifest floor.

## Quick Selection Guide

### I have an NVIDIA GPU
```bash
uv pip install -r requirements/requirements-gpu.txt --index-strategy unsafe-best-match
```
**Requirements:** NVIDIA GPU (4 GB+), driver compatible with CUDA 12.4

### I have an AMD GPU
```bash
uv pip install -r requirements/requirements-rocm.txt --index-strategy unsafe-best-match
```
**Requirements:** ROCm 7.x compatible GPU and driver

### I don't have a GPU or want a minimal installation
```bash
uv pip install -r requirements/requirements-cpu.txt
```
**Requirements:** Any CPU, slower AI processing

### I want it to work everywhere (recommended for most users)
```bash
uv pip install -r requirements/requirements.txt
```
**Requirements:** Any system; install a GPU override later to upgrade

### I'm running on a Linux server
```bash
uv pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match
```
**Requirements:** Linux system, CUDA-capable for GPU use

## Installation Instructions

### Standard Installation

```bash
# Clone repository
git clone https://github.com/BarbellDwarf/SermonPilot.git
cd SermonPilot

# Create virtual environment
uv venv --python 3.11
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

# Install dependencies (choose one)
uv pip install -r requirements/requirements.txt          # Default
uv pip install -r requirements/requirements-gpu.txt      # NVIDIA GPU
uv pip install -r requirements/requirements-rocm.txt     # AMD GPU
uv pip install -r requirements/requirements-cpu.txt      # CPU only
```

GPU and ROCm overrides need `--index-strategy unsafe-best-match` so pip can
pull each package from the wheelhouse that carries the platform suffix.

### Install from the Manifest (Alternative)

```bash
uv sync
```

This installs exactly the locked dependency set from `uv.lock` into the
project virtual environment.

### Configure

```bash
cp .env.example .env          # Fill in your SermonAudio and LLM API keys
```

No `config.yaml` is required. Settings live in a SQLite settings database:
on first launch the environment variables are seeded into it, and the web UI
Settings page edits it from then on. `config/config.example.yaml` is a
reference showing every recognized key, and the Settings page can export the
current settings to YAML or import a YAML file. To force a specific file as
an extra config layer, point `SA_UPDATER_CONFIG` at it. An existing install
that still has a hand-tuned `config.yaml` has its values imported into the
database once, automatically.

### GPU Installation Verification

After installing GPU requirements, verify CUDA is working:

```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python -c "import torch; print(f'CUDA device count: {torch.cuda.device_count()}')"
python -c "import torch; print(torch.__version__)"
```

For ROCm, confirm the build carries the ROCm suffix:

```bash
python -c "import torch; print(torch.__version__)"   # e.g. 2.12.1+rocm7.1
```

## Troubleshooting

### GPU Installation Issues

1. **CUDA version mismatch**: Ensure your NVIDIA driver supports CUDA 12.4
   (the cu124 wheelhouse). `nvidia-smi` shows the driver's CUDA version.
2. **Package conflicts**: Create a fresh virtual environment and use
   `--index-strategy unsafe-best-match` with the override files.
3. **Slow transcription on GPU**: Confirm the torch build is the GPU variant
   (`torch.__version__` shows `+cu124` or `+rocm7.1`) and that
   `torch.cuda.is_available()` returns `True`.

### CPU Fallback

If the GPU install fails, install the CPU wheelhouse to get a working
environment, then retry the GPU install:

```bash
uv pip install -r requirements/requirements-cpu.txt
```

### Memory Issues

For systems with limited memory:

1. Use `requirements/requirements-cpu.txt` for a minimal installation
2. Close other applications during installation
3. Consider installing packages individually

## Upgrading Between Versions

### From CPU to GPU

```bash
uv pip install -r requirements/requirements-gpu.txt --index-strategy unsafe-best-match
```

### Clean Installation (Recommended)

```bash
# Remove existing environment
rm -rf .venv  # Linux/Mac
# OR
rmdir /s .venv  # Windows

# Create fresh environment
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements/requirements-gpu.txt --index-strategy unsafe-best-match
```

## System Requirements Summary

### Minimum (CPU-only)
- Python 3.10+
- 4 GB RAM
- 5 GB disk space
- Any CPU

### Recommended (NVIDIA GPU)
- Python 3.10+
- 8 GB RAM
- NVIDIA GPU (4 GB+ memory)
- 10 GB disk space
- CUDA 12.4 compatible driver

### Recommended (AMD GPU)
- Python 3.10+
- 8 GB RAM
- ROCm 7.x compatible GPU
- 10 GB disk space

Choose the requirements file that best matches your system capabilities and
performance needs. For GPU details, see [GPU_INSTALLATION.md](GPU_INSTALLATION.md).
