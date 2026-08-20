# Requirements Files Guide

`pyproject.toml` is the single source of truth for dependencies. `requirements/requirements.txt` is a derived mirror of the `[project] dependencies` block (regenerate with `uv export --no-dev --format requirements.txt`). The remaining files are per-index overrides for the PyTorch family and convenience installs.

## Directory Structure

```text
requirements/
├── README.md                           # This documentation
├── requirements.txt                    # Derived mirror of pyproject.toml runtime deps
├── requirements-cpu.txt               # CPU-only PyTorch override (CPU index)
├── requirements-gpu.txt                # CUDA PyTorch override (cu124 index)
├── requirements-rocm.txt               # ROCm PyTorch override (rocm7.1 index)
├── requirements-dev.txt               # Development tools (mirror of the [dev] extra)
├── requirements-linux.txt             # Linux convenience install
├── requirements-models-deepfilternet.txt  # DeepFilterNet model extras
├── requirements-models-all.txt        # All AI model extras
├── linux/                             # Linux-specific files
│   └── requirements-models-deepfilternet.txt  # DeepFilterNet (Linux)
└── windows/                           # Windows-specific files
    ├── requirements-windows.txt       # Windows convenience install
    └── requirements-models-deepfilternet.txt  # DeepFilterNet (Windows)
```

## Core Requirements

### `requirements.txt`

Derived mirror of the `[project] dependencies` block in `pyproject.toml`. The Dockerfile and the wheel install the same dependency set.

```bash
uv pip install -r requirements/requirements.txt
```

## PyTorch Index Overrides

The torch family is pinned once in `pyproject.toml` (`torch>=2.6.0`, `torchaudio>=2.6.0`). Each override file adds the matching index and pins the same version with the platform suffix.

### `requirements-cpu.txt`

CPU-only PyTorch builds from the CPU index.

```bash
uv pip install -r requirements/requirements-cpu.txt
```

### `requirements-gpu.txt`

CUDA-enabled PyTorch builds from the cu124 index.

```bash
uv pip install -r requirements/requirements-gpu.txt --index-strategy unsafe-best-match
```

### `requirements-rocm.txt`

ROCm-enabled PyTorch builds from the rocm7.1 index.

```bash
uv pip install -r requirements/requirements-rocm.txt --index-strategy unsafe-best-match
```

## Platform-Specific Files

### Linux (`linux/`)

- **`requirements-linux.txt`**: Linux convenience install with the CUDA index.
- **`requirements-models-deepfilternet.txt`**: DeepFilterNet audio enhancement.

### Windows (`windows/`)

- **`requirements-windows.txt`**: Windows convenience install with the CUDA index.
- **`requirements-models-deepfilternet.txt`**: DeepFilterNet audio enhancement.

## Development Requirements

### `requirements-dev.txt`

Development and testing tools (mirror of the `[dev]` extra in `pyproject.toml`).

```bash
uv pip install -r requirements/requirements-dev.txt
```

## AI Model Requirements

### `requirements-models-deepfilternet.txt`

DeepFilterNet model extras (already part of the base runtime deps; kept for standalone installs).

### `requirements-models-all.txt`

All AI enhancement models combined.

```bash
uv pip install -r requirements/requirements-models-all.txt
```

## Installation Recommendations

### For Development (Linux with GPU)

```bash
# Activate virtual environment
source .venv/bin/activate

# Install base + GPU + models
uv pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match
uv pip install -r requirements/linux/requirements-models-deepfilternet.txt
uv pip install -r requirements/requirements-dev.txt
```

### For Development (Windows with GPU)

```bash
# Activate virtual environment
.venv\Scripts\activate

# Install base + GPU + models
uv pip install -r requirements/windows/requirements-windows.txt --index-strategy unsafe-best-match
uv pip install -r requirements/windows/requirements-models-deepfilternet.txt
uv pip install -r requirements/requirements-dev.txt
```

### For Production (CPU-only)

```bash
uv pip install -r requirements/requirements-cpu.txt
```

### For Production (GPU-enabled)

```bash
uv pip install -r requirements/requirements-gpu.txt --index-strategy unsafe-best-match
uv pip install -r requirements/linux/requirements-models-deepfilternet.txt  # or windows/
```

## System Requirements

### GPU Installation

- NVIDIA GPU with CUDA Compute Capability 3.5+
- CUDA 12.4 compatible driver
- 4GB+ GPU memory (8GB+ recommended for full acceleration)

### CPU Installation

- No special hardware requirements
- Will automatically use CPU versions of all packages

## Platform-Specific Notes

### Linux

- **Package Manager**: Use `apt`, `yum`, or `pacman` for system dependencies
- **FFmpeg**: Install via package manager
- **CUDA**: Install NVIDIA drivers and CUDA toolkit

### Windows

- **FFmpeg**: Download from [ffmpeg.org](https://ffmpeg.org/download.html)
- **CUDA**: Install NVIDIA drivers and CUDA toolkit
- **Visual Studio**: May be required for some packages

## Troubleshooting

### Common Issues

1. **Packaging conflicts**: Use `--index-strategy unsafe-best-match`
2. **CUDA compatibility**: Ensure NVIDIA drivers match CUDA 12.4
3. **Model installation**: Some AI models may need manual installation
4. **Virtual environment**: Always install within `.venv`

### Manual Model Installation

Some AI models have complex dependencies and may need manual installation:

```bash
# VoiceFixer
pip install voicefixer

# SpeechBrain
pip install speechbrain

# Demucs
pip install demucs
```
