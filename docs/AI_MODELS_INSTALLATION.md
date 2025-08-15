# Enhanced Installation Guide for AI Models

## Core Installation

First, install the base dependencies:

```bash
# Install core dependencies
uv pip install -r requirements.txt

# OR using pip
pip install -r requirements.txt
```

## AI Model Installation

### DeepFilterNet (Included)
DeepFilterNet is included in the core dependencies and should work out of the box.

### Resemble Enhance (Manual Installation)
Resemble Enhance requires special handling due to its deepspeed dependency:

#### Method 1: Direct Installation (Recommended)
```bash
# Install PyTorch first (if not already installed)
pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu121

# Install resemble-enhance
pip install resemble-enhance
```

#### Method 2: Without DeepSpeed (Inference Only)
If you encounter build issues with deepspeed, you can try:
```bash
# Install without build dependencies
pip install resemble-enhance --no-deps --force-reinstall

# Then install only the runtime dependencies manually
pip install torch torchaudio torchvision celluloid librosa matplotlib numpy omegaconf pandas ptflops rich scipy soundfile tqdm resampy tabulate gradio
```

#### Method 3: Pre-built Wheels (Linux)
```bash
# Use pre-built wheels to avoid compilation
pip install resemble-enhance --only-binary=all
```

### Optional AI Models

#### VoiceFixer
```bash
pip install voicefixer
```

#### SpeechBrain
```bash
pip install speechbrain
```

#### Demucs
```bash
pip install demucs
```

## Platform-Specific Considerations

### Linux
```bash
# Install system dependencies first
sudo apt update && sudo apt install -y \
    ffmpeg libsndfile1 portaudio19-dev \
    python3-dev build-essential

# Then install AI models
pip install resemble-enhance
```

### Windows
```bash
# Install Visual Studio Build Tools if needed
# Then install normally
pip install resemble-enhance
```

### macOS
```bash
# Install Xcode command line tools
xcode-select --install

# Then install normally
pip install resemble-enhance
```

## Troubleshooting

### DeepSpeed Build Failures
If deepspeed fails to build:

1. **Install PyTorch first**:
   ```bash
   pip install torch torchaudio torchvision
   ```

2. **Use CPU-only PyTorch**:
   ```bash
   pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cpu
   ```

3. **Skip deepspeed for inference**:
   ```bash
   pip install resemble-enhance --no-deps
   # Install dependencies manually (excluding deepspeed)
   ```

### Memory Issues
For systems with limited memory:
```bash
# Set environment variables
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128
export OMP_NUM_THREADS=4
```

### CUDA Issues
```bash
# Check CUDA availability
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Install CUDA-specific PyTorch
pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu121
```

## Verification

Test your installation:

```bash
# Test DeepFilterNet
python -c "from df import enhance; print('DeepFilterNet: OK')"

# Test Resemble Enhance (if installed)
python -c "from resemble_enhance.enhancer.inference import denoise; print('Resemble Enhance: OK')"

# Test PyTorch
python -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
```

## Performance Notes

- **DeepFilterNet**: Fast, reliable, good for production
- **Resemble Enhance**: Highest quality, but requires more resources and complex installation
- **VoiceFixer**: Good quality, moderate speed
- **SpeechBrain**: Good for specific tasks, can be memory-intensive

Choose the model that best fits your needs and system capabilities.
