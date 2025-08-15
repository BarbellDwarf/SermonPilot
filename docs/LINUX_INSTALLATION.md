# Linux Installation Guide

## System Requirements

### Ubuntu/Debian
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y \
    python3 python3-pip python3-venv \
    ffmpeg libsndfile1 libasound2-dev portaudio19-dev \
    build-essential pkg-config \
    git curl

# For NVIDIA GPU support (optional)
sudo apt install -y nvidia-driver-535 nvidia-cuda-toolkit
```

### CentOS/RHEL/Fedora
```bash
# For CentOS/RHEL
sudo yum install -y python3 python3-pip python3-devel \
    ffmpeg libsndfile portaudio-devel \
    gcc gcc-c++ make \
    git curl

# For Fedora
sudo dnf install -y python3 python3-pip python3-devel \
    ffmpeg libsndfile portaudio-devel \
    gcc gcc-c++ make \
    git curl
```

### Arch Linux
```bash
sudo pacman -S python python-pip \
    ffmpeg libsndfile portaudio \
    base-devel \
    git curl

# For NVIDIA GPU support
sudo pacman -S nvidia nvidia-utils cuda
```

## Python Environment Setup

### Using UV (Recommended)
```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Create virtual environment
uv venv --python 3.11
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements-linux.txt
```

### Using Standard Python
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies (GPU support)
pip install -r requirements-linux.txt

# OR for CPU-only
pip install -r requirements-cpu.txt
```

## Platform-Specific Installation

### GPU (CUDA) Installation
```bash
# Install CUDA-enabled PyTorch
pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu121

# Install remaining dependencies
pip install -r requirements.txt
```

### CPU-Only Installation
```bash
# Install CPU-only PyTorch
pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies  
pip install -r requirements.txt
```

## Verification

```bash
# Test PyTorch installation
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"

# Test audio processing
python -c "import soundfile as sf; print('Audio processing: OK')"

# Test AI models
python -c "from df import enhance; print('DeepFilterNet: OK')"
python -c "from resemble_enhance.enhancer.inference import denoise; print('Resemble Enhance: OK')"
```

## Troubleshooting

### Common Issues

1. **CUDA not detected**:
   ```bash
   # Check NVIDIA driver
   nvidia-smi
   
   # Reinstall CUDA PyTorch
   pip uninstall torch torchaudio torchvision
   pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu121
   ```

2. **Audio libraries missing**:
   ```bash
   # Ubuntu/Debian
   sudo apt install -y ffmpeg libsndfile1 portaudio19-dev
   
   # CentOS/RHEL  
   sudo yum install -y ffmpeg libsndfile portaudio-devel
   ```

3. **Permission issues**:
   ```bash
   # Don't use sudo with pip, use virtual environment
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Build failures**:
   ```bash
   # Install build dependencies
   sudo apt install -y build-essential python3-dev
   
   # Or use pre-compiled wheels
   pip install --only-binary=all -r requirements.txt
   ```

## Performance Optimization

### For Production
```bash
# Install with performance optimizations
pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu121
export TORCH_CUDA_ARCH_LIST="7.0;7.5;8.0;8.6"  # Set for your GPU
```

### Memory Management
```bash
# For low-memory systems
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128
```

## Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/ -v

# Check code formatting
black --check .
ruff check .
```
