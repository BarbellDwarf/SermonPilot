# GPU Installation Guide

This guide covers installing SermonPilot with GPU acceleration for audio
enhancement and transcription. It covers NVIDIA CUDA, AMD ROCm, CPU-only
setups, and Docker images built for each backend.

## How GPU acceleration is used

- **DeepFilterNet** runs on PyTorch and uses CUDA when
  `torch.cuda.is_available()` is true, with automatic ROCm detection via
  `torch.version.hip`.
- **Clear** (the `clear-studio` and `clear-natural` methods) runs through
  ONNX Runtime, which supports CUDA, ROCm, and CPU.
- **Local transcription** (faster-whisper) benefits from GPU compute.

The manifest in `pyproject.toml` requires `torch>=2.6.0`,
`torchaudio>=2.6.0`, and `torchvision>=0.20.0`. Any PyTorch install must
satisfy that floor. Some `requirements/` files still pin older CUDA builds
(see [PyTorch version note](#pytorch-version-note) below).

## Choose an installation

| Scenario | What to install |
|----------|-----------------|
| Standard (auto-detects, may use GPU if present) | `requirements/requirements.txt` |
| NVIDIA GPU, CUDA 12.x | CUDA PyTorch builds (below) |
| AMD GPU, ROCm 7.x | `requirements/requirements-rocm.txt` |
| CPU-only | `requirements/requirements-cpu.txt` |

## Setup

### 1. Create and activate a virtual environment

```bash
uv venv --python 3.11
source .venv/bin/activate  # Linux/Mac
```

Windows activation:

```bash
.venv\Scripts\activate
```

### 2. Install the base requirements

```bash
uv pip install -r requirements/requirements.txt
```

Or install from the manifest and lockfile:

```bash
uv sync
```

### 3. Install GPU PyTorch

Install PyTorch from the wheelhouse that matches your CUDA version. CUDA
12.x users typically use `cu124` or `cu126`; older toolchains use `cu118`
or `cu121`. The install commands stay at or above the manifest floor:

```bash
# NVIDIA CUDA (replace cu124 with your CUDA wheelhouse)
uv pip install "torch>=2.6.0" "torchaudio>=2.6.0" "torchvision>=0.20.0" \
  --extra-index-url https://download.pytorch.org/whl/cu124 \
  --index-strategy unsafe-best-match
```

For AMD GPUs, install from the ROCm 7.1 wheelhouse instead:

```bash
uv pip install -r requirements/requirements-rocm.txt
```

That file pins `torch==2.12.1+rocm7.1`, `torchaudio==2.11.0+rocm7.1`, and
`torchvision==0.27.1+rocm7.1`, which satisfy the manifest floor.

### 4. Verify the installation

```bash
python -c "import torch; print(f'PyTorch version: {torch.__version__}')"
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
nvidia-smi
```

Importing `src/audio_processing.py` prints the detected device, for example
`CUDA available: True` and `CUDA device: NVIDIA GeForce RTX 4060`.

## PyTorch version note

`requirements/requirements-gpu.txt`, `requirements-gpu-minimal.txt`, and
`requirements-gpu-full.txt` pin `torch==2.1.1+cu121` builds, which predate
the `torch>=2.6.0` floor in `pyproject.toml`. If you install from those
files, upgrade PyTorch afterwards with the CUDA install command in
[step 3](#3-install-gpu-pytorch) so the environment satisfies the manifest.

## Torch upgrade / venv rebuild

Two open PyTorch advisories are accepted as of v1.6.0:

- **GHSA-rrmf-rvhw-rf47** (CVE-2025-3000): memory corruption through
  `torch.jit.script`. Affects all torch releases up to 2.12.1 and is fixed
  only in 2.13.0. Low severity, local attack.
- **GHSA-vgrw-7cvw-pwgx** (CVE-2025-2999): memory corruption through
  `torch.nn.utils.rnn.unpack_sequence`. Affects all releases before 2.9.1
  and is fixed in 2.9.1. Medium severity, local attack.

The torch pins in `pyproject.toml` and `requirements/` stay unchanged
because no build that fixes both advisories is compatible with the
verified ROCm setup. The verified-clean build (no chunked-audio
corruption, issue #41) is `torch==2.11.0.dev20260206+rocm7.0` from the
rocm7.0 nightly index, which is also the newest build that index
publishes. The only fully patched build, torch 2.13.0, ships ROCm
wheels only as `+rocm7.1` and `+rocm7.2`; it sits on the same
2.12/2.13 line as the corrupting `2.12.0+rocm7.14.0` and has not passed
the regression gate below, so upgrading to it would risk reintroducing
issue #41.

To reproduce the verified working setup:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements/requirements.txt
uv pip install "torch==2.11.0.dev20260206+rocm7.0" \
  "torchaudio==2.11.0.dev20260216+rocm7.0" \
  --extra-index-url https://download.pytorch.org/whl/nightly/rocm7.0 \
  --index-strategy unsafe-best-match
```

Before adopting any newer torch (the candidate that fixes both
advisories is `torch==2.13.0+rocm7.1`), run the chunked-enhancement
stability gate on the ROCm machine:

1. Take a 7-minute slice of a sermon recording and enhance it in a
   single pass.
2. Enhance the same slice in 60-second chunks, three times.
3. Cross-correlate each chunked output against the single-pass output;
   all three trials must score 0.999 or higher.
4. Run the full 42-minute pipeline and confirm it completes without
   corruption.

Only after the gate passes should the pin be raised in `pyproject.toml`
and the `requirements/` override files.

## Docker

### Build with a GPU backend

```bash
docker build --build-arg GPU_BACKEND=cuda -t sermonpilot:latest .
```

Backends: `cpu` (default), `cuda`, `rocm`. The `cuda` build installs
`onnxruntime-gpu`; the `rocm` build installs `requirements-rocm.txt`.

### Run with a GPU image

Prebuilt images carry a backend suffix, for example `v1.5.3-cuda` or
`v1.5.3-rocm`. The `latest` tag points at the latest CUDA build.

```bash
SERMONPILOT_TAG=v1.5.3-cuda docker compose up -d
```

Add device access in `docker-compose.yml`:

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

For ROCm:

```yaml
services:
  sermon-pilot:
    devices:
      - /dev/kfd
      - /dev/dri
```

Install the NVIDIA Container Toolkit (or ROCm Docker setup) on the host
first. Verify GPU access inside the container:

```bash
docker compose exec sermon-pilot nvidia-smi
```

## System requirements

### NVIDIA

- NVIDIA GPU with a CUDA-capable driver
- Driver version compatible with the CUDA wheelhouse you install
- 4 GB+ GPU memory (8 GB+ recommended)

### AMD

- ROCm 7.x compatible GPU and driver
- 4 GB+ GPU memory (8 GB+ recommended)

### CPU-only

- No special hardware requirements
- Install `requirements/requirements-cpu.txt` to force CPU PyTorch builds

## Selecting a GPU

Use the standard CUDA environment variable to restrict which devices the
process sees:

```bash
CUDA_VISIBLE_DEVICES=0 python sermon_updater.py new-sermon audio.mp3 --speaker "Speaker" --date "2024-01-15"
```

## Configuration

Audio enhancement is configured through `config.yaml`:

```yaml
audio_enhancement_method: deepfilternet  # deepfilternet, clear-studio, clear-natural, custom, none
clear_model_variant: natural             # Clear model variant when using Clear
clear_custom_repo: ""                    # Custom Clear model repo (method: custom)
clear_custom_file: ""                    # Custom Clear model file (method: custom)
audio_noise_reduction: true
audio_normalize: true
audio_target_level_db: -22.0
audio_gain_db: 0.5
```

DeepFilterNet needs PyTorch with CUDA or ROCm support. Clear methods use
ONNX Runtime and work on CUDA, ROCm, or CPU without PyTorch. Set the
enhancement method to `none` to skip enhancement entirely.

## Troubleshooting

**CUDA is reported as unavailable.** Check the driver and toolkit:

```bash
nvidia-smi
```

Confirm the installed PyTorch build matches the CUDA version of the driver.
Reinstall with the matching wheelhouse from
[step 3](#3-install-gpu-pytorch).

**Out of memory during processing.** Close other GPU applications, reduce
the transcription model size in `config.yaml`
(`transcription.faster_whisper_local.model` or `transcription.whisper_local.model`),
or use a smaller enhancement model. Clear ONNX inference generally uses less
memory than DeepFilterNet.

**Import errors after switching builds.** Reinstall the base requirements:

```bash
uv pip install -r requirements/requirements.txt
```

**Slow processing on a GPU machine.** Verify the GPU is actually used by
checking the startup output of `src/audio_processing.py` (look for
`CUDA available: True`) and watch utilization while processing:

```bash
nvidia-smi -l 2
```

**CPU fallback after a failed GPU install.** Install the CPU wheelhouse to
get a working environment, then retry the GPU install:

```bash
uv pip install -r requirements/requirements-cpu.txt
```

## Getting help

1. Check the system requirements above.
2. Confirm the driver, CUDA version, and PyTorch build match.
3. Verify with the commands in [step 4](#4-verify-the-installation).
4. Fall back to CPU if needed.
5. Report issues with the output of `nvidia-smi` and the verification
   commands.
