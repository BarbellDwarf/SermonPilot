# Requirements Files Guide

This directory contains various requirement files for different platforms and installation scenarios.

## Directory Structure

```text
requirements/
├── README.md                           # This documentation
├── requirements.txt                    # Core dependencies (all platforms)
├── requirements-cpu.txt               # CPU-only (all platforms)
├── requirements-gpu-minimal.txt       # Basic GPU (all platforms)
├── requirements-gpu.txt               # Standard GPU (all platforms)
├── requirements-gpu-full.txt          # Full GPU acceleration (all platforms)
├── requirements-dev.txt               # Development tools (all platforms)
├── linux/                             # Linux-specific files
│   ├── requirements-linux.txt         # Linux base requirements
│   └── requirements-models-deepfilternet.txt  # DeepFilterNet (Linux)
└── windows/                           # Windows-specific files
    ├── requirements-windows.txt       # Windows base requirements
    └── requirements-models-deepfilternet.txt  # DeepFilterNet (Windows)
```

## Core Requirements

### `requirements.txt`

Base requirements for all platforms. Contains all essential dependencies for the SermonAudio processor.

```bash
uv pip install -r requirements.txt
```

## Platform-Specific Requirements

### Linux (`linux/`)

#### `requirements-linux.txt`

Linux-specific requirements with GPU support via CUDA 12.1.

```bash
uv pip install -r requirements/linux/requirements-linux.txt --index-strategy unsafe-best-match
```

#### Model Files (Linux)

- **`requirements-models-deepfilternet.txt`**: DeepFilterNet audio enhancement

### Windows (`windows/`)

#### `requirements-windows.txt`

Windows-specific requirements with GPU support via CUDA 12.1.

```bash
uv pip install -r requirements/windows/requirements-windows.txt --index-strategy unsafe-best-match
```

#### Model Files (Windows)

- **`requirements-models-deepfilternet.txt`**: DeepFilterNet audio enhancement

## GPU Acceleration Levels

### `requirements-gpu-minimal.txt`

Minimal GPU support with essential CUDA packages.

- Basic PyTorch GPU acceleration
- GPU monitoring
- Memory management

```bash
uv pip install -r requirements/requirements-gpu-minimal.txt
```

### `requirements-gpu.txt`

Standard GPU installation with enhanced acceleration.

- Full PyTorch GPU stack
- GPU monitoring and profiling
- Memory optimization
- Compatible with all AI models

```bash
uv pip install -r requirements/requirements-gpu.txt --index-strategy unsafe-best-match
```

### `requirements-gpu-full.txt`

Complete GPU acceleration with all optional packages.

- Maximum performance (~4-8GB download)
- Advanced GPU monitoring
- Distributed computing support
- All GPU-accelerated libraries

```bash
uv pip install -r requirements/requirements-gpu-full.txt
```

## AI Model Requirements

### `requirements-models-all.txt`

All AI enhancement models combined.

```bash
uv pip install -r requirements/requirements-models-all.txt
```

## Development Requirements

### `requirements-dev.txt`

Development and testing dependencies.

```bash
uv pip install -r requirements/requirements-dev.txt
```

## Installation Recommendations

### For Development (Linux with GPU)

```bash
# Activate virtual environment
source .venv/bin/activate

# Install base + GPU + models
uv pip install -r requirements/linux/requirements-linux.txt --index-strategy unsafe-best-match
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
- CUDA 12.1 compatible driver
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
2. **CUDA compatibility**: Ensure NVIDIA drivers match CUDA 12.1
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
