# Installation Guide - Requirements Files

This repository provides multiple requirements files for different installation scenarios. Choose the appropriate file based on your hardware and performance needs.

## 📋 Available Requirements Files

### 1. `requirements/requirements.txt` (Default - Automatic Detection)
**Best for:** Most users, development, automatic hardware detection
```bash
pip install -r requirements/requirements.txt
```
- **CPU fallback with GPU detection**: Installs CPU versions but allows GPU upgrade
- **Moderate size**: ~2-3GB installation
- **Compatible**: Works on all systems
- **Performance**: Good CPU performance, can be upgraded to GPU later

### 2. `requirements/requirements-cpu.txt` (CPU-Only)
**Best for:** Servers without GPU, testing, low-resource environments
```bash
pip install -r requirements/requirements-cpu.txt
```
- **CPU-only**: Explicitly installs CPU-only versions
- **Smallest size**: ~1-2GB installation
- **Compatible**: Works on all systems
- **Performance**: CPU-only, slower AI processing

### 3. `requirements/requirements-gpu.txt` (GPU Accelerated)
**Best for:** Users with NVIDIA GPUs, production environments
```bash
pip install -r requirements/requirements-gpu.txt
```
- **GPU acceleration**: CUDA 12.1 support
- **Moderate GPU size**: ~3-4GB installation
- **Requirements**: NVIDIA GPU with 4GB+ memory
- **Performance**: Significantly faster AI processing

### 4. `requirements/requirements-gpu-full.txt` (Maximum GPU Acceleration)
**Best for:** High-end systems, research, maximum performance
```bash
pip install -r requirements/requirements-gpu-full.txt
```
- **Full GPU acceleration**: All available GPU optimizations
- **Large size**: ~6-8GB installation
- **Requirements**: NVIDIA GPU with 8GB+ memory, 16GB+ system RAM
- **Performance**: Maximum possible performance

### 5. `requirements/requirements-linux.txt` (Linux-Specific)
**Best for:** Linux servers, containerized deployments
```bash
pip install -r requirements/requirements-linux.txt
```
- **Linux optimizations**: Platform-specific packages
- **Server-friendly**: Headless operation support
- **Docker compatible**: Works in containers

### 6. `requirements/requirements-dev.txt` (Development)
**Best for:** Contributors, debugging, development work
```bash
pip install -r requirements/requirements-dev.txt
```
- **Development tools**: Testing, linting, formatting
- **Debugging**: Profiling and analysis tools
- **Code quality**: Pre-commit hooks, type checking

## 🎯 Quick Selection Guide

### I want maximum performance and have a powerful GPU
```bash
pip install -r requirements/requirements-gpu-full.txt
```
**Requirements:** NVIDIA GPU (8GB+), 16GB+ RAM, 20GB+ disk space

### I have an NVIDIA GPU but want a lighter installation
```bash
pip install -r requirements/requirements-gpu.txt
```
**Requirements:** NVIDIA GPU (4GB+), 8GB+ RAM, 10GB+ disk space

### I want it to work everywhere (recommended for most users)
```bash
pip install -r requirements/requirements.txt
```
**Requirements:** Any system, will use GPU if available

### I don't have a GPU or want minimal installation
```bash
pip install -r requirements/requirements-cpu.txt
```
**Requirements:** Any CPU, slower AI processing

### I'm running on Linux server
```bash
pip install -r requirements/requirements-linux.txt
```
**Requirements:** Linux system, optimized for server deployment

## 🔧 Installation Instructions

### Standard Installation
```bash
# Clone repository
git clone https://github.com/SpirusNox/SermonPilot.git
cd SermonPilot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

# Install dependencies (choose one)
pip install -r requirements/requirements.txt          # Default
pip install -r requirements/requirements-gpu.txt      # GPU accelerated
pip install -r requirements/requirements-gpu-full.txt # Maximum performance
pip install -r requirements/requirements-cpu.txt      # CPU only
```

### UV Package Manager (Recommended)
```bash
# Install UV
pip install uv

# Create environment and install
uv venv --python 3.11
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

# Install dependencies
uv pip install -r requirements/requirements-gpu.txt  # or your chosen file
```

### GPU Installation Verification
After installing GPU requirements, verify CUDA is working:
```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA device count: {torch.cuda.device_count()}")
if torch.cuda.is_available():
    print(f"CUDA device: {torch.cuda.get_device_name(0)}")
```

## 🚨 Troubleshooting

### GPU Installation Issues
1. **CUDA version mismatch**: Ensure your NVIDIA driver supports CUDA 12.1+
2. **Out of memory**: Use `requirements/requirements-gpu.txt` instead of `requirements-gpu-full.txt`
3. **Package conflicts**: Create a fresh virtual environment

### CPU Fallback
If GPU installation fails, automatically fallback:
```bash
pip install -r requirements/requirements-cpu.txt
```

### Memory Issues
For systems with limited memory:
1. Use `requirements/requirements-cpu.txt` for minimal installation
2. Close other applications during installation
3. Consider installing packages individually

## 📊 Performance Comparison

| Requirements File | Installation Size | GPU Memory | Performance | Use Case |
|-------------------|------------------|------------|-------------|----------|
| `requirements/requirements.txt` | ~2-3GB | 2GB+ | Good | General use |
| `requirements/requirements-cpu.txt` | ~1-2GB | N/A | Basic | CPU-only |
| `requirements/requirements-gpu.txt` | ~3-4GB | 4GB+ | Fast | GPU users |
| `requirements/requirements-gpu-full.txt` | ~6-8GB | 8GB+ | Maximum | High-end systems |

## 🔄 Upgrading Between Versions

### From CPU to GPU
```bash
pip install -r requirements/requirements-gpu.txt --force-reinstall
```

### From Basic GPU to Full GPU
```bash
pip install -r requirements/requirements-gpu-full.txt --upgrade
```

### Clean Installation (Recommended)
```bash
# Remove existing environment
rm -rf .venv  # Linux/Mac
# OR
rmdir /s .venv  # Windows

# Create fresh environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/requirements-gpu.txt
```

## 📋 System Requirements Summary

### Minimum (CPU-only)
- Python 3.9+
- 4GB RAM
- 5GB disk space
- Any CPU

### Recommended (GPU)
- Python 3.11+
- 8GB RAM
- NVIDIA GPU (4GB+ memory)
- 10GB disk space
- CUDA 12.1+ compatible driver

### High-Performance (Full GPU)
- Python 3.11+
- 16GB+ RAM
- NVIDIA GPU (8GB+ memory)
- 20GB+ disk space
- CUDA 12.1+ compatible driver

Choose the requirements file that best matches your system capabilities and performance needs!
