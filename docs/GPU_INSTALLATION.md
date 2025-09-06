# GPU | File | Purpose | GPU Memory | Install Size | Use Case |
|------|---------|------------|--------------|----------|
| `requirements/requirements.txt` | Basic CPU/GPU auto-detect | Any | ~2GB | Standard installation |
| `requirements/requirements-cpu.txt` | CPU-only operation | None | ~1.5GB | No GPU or compatibility issues |
| `requirements/requirements-gpu-minimal.txt` | Essential GPU support | 4GB+ | ~3GB | Basic GPU acceleration |
| `requirements/requirements-gpu.txt` | Full GPU acceleration | 6GB+ | ~4GB | Recommended GPU setup |
| `requirements/requirements-gpu-full.txt` | Maximum acceleration | 8GB+ | ~8GB | Research/production use |ation Guide

This guide helps you choose the right requirements file for your system and explains how to install GPU acceleration for the SermonAudio AI Audio Processor.

## 📋 Requirements Files Overview

| File | Purpose | GPU Memory | Install Size | Use Case |
|------|---------|------------|--------------|----------|
| `requirements/requirements/requirements.txt` | Basic CPU/GPU auto-detect | Any | ~2GB | Standard installation |
| `requirements/requirements/requirements-cpu.txt` | CPU-only operation | None | ~1.5GB | No GPU or compatibility issues |
| `requirements/requirements/requirements-gpu-minimal.txt` | Essential GPU support | 4GB+ | ~3GB | Basic GPU acceleration |
| `requirements/requirements/requirements-gpu.txt` | Full GPU acceleration | 6GB+ | ~4GB | Recommended GPU setup |
| `requirements/requirements/requirements-gpu-full.txt` | Maximum acceleration | 8GB+ | ~8GB | Research/production use |

## 🎯 Quick Start - Choose Your Installation

### 1. **Most Users** (Recommended)
```bash
# Activate your virtual environment
uv venv --python 3.11
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

# Install with automatic GPU detection
uv pip install -r requirements/requirements.txt
```

### 2. **GPU Users** (Recommended for NVIDIA GPU owners)
```bash
# For standard GPU acceleration
uv pip install -r requirements/requirements-gpu.txt

# OR for minimal GPU support (if you have compatibility issues)
uv pip install -r requirements/requirements-gpu-minimal.txt

# OR for Linux with GPU support (requires special flag for dependency resolution)
uv pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match
```

### 3. **High-Performance Users**
```bash
# For maximum GPU acceleration (large download)
uv pip install -r requirements/requirements-gpu-full.txt
```

### 4. **CPU-Only Users**
```bash
# For systems without GPU or compatibility issues
uv pip install -r requirements/requirements-cpu.txt
```

## 🔧 GPU Requirements

### Minimum Requirements
- **GPU**: NVIDIA GPU with CUDA Compute Capability 3.5+
- **Driver**: CUDA 12.1 compatible driver (typically 530+)
- **Memory**: 4GB GPU memory (6GB+ recommended)
- **System RAM**: 8GB+ (16GB+ recommended for large models)

### Recommended Requirements
- **GPU**: RTX 3060/4060 or better, Tesla T4, A100, etc.
- **Memory**: 8GB+ GPU memory
- **System RAM**: 16GB+
- **Storage**: 10GB+ free space for models

### Check GPU Compatibility
```bash
# Check if CUDA is available
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Check GPU details
python -c "import torch; print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"No GPU\"}')"

# Check CUDA version
nvidia-smi
```

## 🚀 Installation Steps

### Step 1: Create Virtual Environment
```bash
# Using UV (recommended)
uv venv --python 3.11 .venv

# Using standard Python
python -m venv .venv
```

### Step 2: Activate Environment
```bash
# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### Step 3: Choose and Install Requirements
```bash
# Choose ONE of these based on your needs:

# Standard installation (auto-detects GPU)
uv pip install -r requirements/requirements.txt

# GPU-optimized installation
uv pip install -r requirements/requirements-gpu.txt

# Minimal GPU installation
uv pip install -r requirements/requirements-gpu-minimal.txt

# Maximum performance installation
uv pip install -r requirements/requirements-gpu-full.txt

# CPU-only installation
uv pip install -r requirements/requirements-cpu.txt
```

### Step 4: Verify Installation
```bash
# Test the installation
python -c "import torch; print(f'PyTorch version: {torch.__version__}')"
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Test audio processing
python -c "import torchaudio; print(f'TorchAudio version: {torchaudio.__version__}')"
```

## 🔄 Switching Between CPU and GPU

You can switch between CPU and GPU installations:

### From CPU to GPU
```bash
# Install GPU version (will upgrade packages)
uv pip install -r requirements/requirements-gpu.txt
```

### From GPU to CPU
```bash
# Uninstall GPU PyTorch
uv pip uninstall torch torchaudio torchvision

# Install CPU version
uv pip install -r requirements/requirements-cpu.txt
```

## 🐛 Troubleshooting

### Common Issues

#### 1. CUDA Version Mismatch
```bash
# Check CUDA version
nvidia-smi

# If you have CUDA 11.x, use:
uv pip install torch==2.1.1+cu118 torchaudio==2.1.1+cu118 torchvision==0.16.1+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
```

#### 2. Out of Memory Errors
- Use `requirements/requirements-gpu-minimal.txt` instead of full version
- Reduce batch sizes in configuration
- Close other GPU applications

#### 3. Import Errors
```bash
# Reinstall with force
uv pip install -r requirements/requirements-gpu.txt --force-reinstall

# Or try CPU fallback
uv pip install -r requirements/requirements-cpu.txt
```

#### 4. Slow Performance
- Verify GPU is being used: Check logs for "Using device: cuda"
- Update GPU drivers
- Check GPU memory usage: `nvidia-smi`

### Performance Testing
```bash
# Test GPU acceleration
python tests/test_audio_upscaling.py

# Run benchmark
python -c "
import torch
import time
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f'Using device: {device}')
x = torch.randn(1000, 1000, device=device)
start = time.time()
y = torch.matmul(x, x)
end = time.time()
print(f'Matrix multiplication time: {end-start:.4f}s')
"
```

## 📊 Performance Comparison

| Operation | CPU (seconds) | GPU (seconds) | Speedup |
|-----------|---------------|---------------|---------|
| Audio Enhancement | 45-60 | 8-15 | 3-7x |
| Transcript Generation | 120-180 | 20-40 | 4-8x |
| Validation (100 sermons) | 300-600 | 60-120 | 4-8x |

## 🔧 Advanced Configuration

### Custom CUDA Version
If you need a specific CUDA version, modify the PyTorch installation:

```bash
# For CUDA 11.8
--extra-index-url https://download.pytorch.org/whl/cu118
torch==2.1.1+cu118
torchaudio==2.1.1+cu118
torchvision==0.16.1+cu118

# For CUDA 12.1 (default)
--extra-index-url https://download.pytorch.org/whl/cu121
torch==2.1.1+cu121
torchaudio==2.1.1+cu121
torchvision==0.16.1+cu121
```

### Memory Optimization
Add to your configuration:
```yaml
# config.yaml
gpu_memory_fraction: 0.8  # Use 80% of GPU memory
mixed_precision: true     # Enable mixed precision training
gradient_checkpointing: true  # Trade compute for memory
```

## 🆘 Getting Help

If you encounter issues:

1. **Check system requirements** above
2. **Try minimal installation** first: `requirements/requirements-gpu-minimal.txt`
3. **Check GPU compatibility** with the verification commands
4. **Fall back to CPU** if needed: `requirements/requirements-cpu.txt`
5. **Report issues** with full error logs and system information

For more help, check the main README.md or open an issue on GitHub.
