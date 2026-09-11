# GPU Installation Guide

This guide covers installing SermonPilot with GPU acceleration for audio
enhancement and transcription. It covers NVIDIA CUDA, AMD ROCm, CPU-only
setups, and Docker images built for each backend.

## How GPU acceleration is used

- **DeepFilterNet** runs on PyTorch and uses CUDA when
  `torch.cuda.is_available()` is true, with automatic ROCm detection via
  `torch.version.hip`.
- **Clear** (the `clear-studio` and `clear-natural` methods) runs through
  ONNX Runtime, which supports CUDA and CPU. On ROCm 7.x systems it runs on
  CPU: the published `onnxruntime-rocm` wheels are built against the ROCm
  6.4.2 ABI and are incompatible with ROCm 7.x (see the note in
  `requirements/requirements-rocm.txt`), which is fast enough for
  sermon-length audio.
- **Local transcription** depends on the backend:
  - `whisper_local` (openai-whisper) runs on torch, so it uses NVIDIA CUDA
    and AMD ROCm GPUs (ROCm exposes HIP through the CUDA device interface).
  - `faster_whisper_local` runs on CTranslate2, which has no ROCm support.
    `src/transcription.py` calls `_detect_device(allow_rocm=False)` for this
    backend, so on an AMD GPU it is forced to CPU (int8) instead of failing
    with "CUDA driver version is insufficient".

The manifest in `pyproject.toml` requires `torch>=2.6.0` and
`torchaudio>=2.6.0`. Any PyTorch install must satisfy that floor. The
`requirements/` override files pin builds that do (see
[PyTorch version note](#pytorch-version-note) below).

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
12.x users typically use `cu124` (what `requirements/requirements-gpu.txt`
pins) or `cu126`. Whichever wheelhouse you pick, it must carry builds at or
above the manifest floor:

```bash
# NVIDIA CUDA (replace cu124 with your CUDA wheelhouse)
uv pip install "torch>=2.6.0" "torchaudio>=2.6.0" \
  --extra-index-url https://download.pytorch.org/whl/cu124 \
  --index-strategy unsafe-best-match
```

For AMD GPUs, install from the ROCm 7.1 wheelhouse instead:

```bash
uv pip install -r requirements/requirements-rocm.txt
```

That file pins `torch==2.12.1+rocm7.1` and `torchaudio==2.11.0+rocm7.1`,
which satisfy the manifest floor. (torch and torchaudio release independently
on the ROCm index, so the versions differ.)

### 4. Verify the installation

```bash
python -c "import torch; print(f'PyTorch version: {torch.__version__}')"
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
nvidia-smi
```

Importing `src/audio_processing.py` prints the detected device, for example
`CUDA available: True` and `CUDA device: NVIDIA GeForce RTX 4060`.

## PyTorch version note

All `requirements/` override files pin builds at or above the
`torch>=2.6.0` floor in `pyproject.toml`:

- `requirements/requirements-gpu.txt` pins `torch==2.6.0+cu124` from the
  cu124 index
- `requirements/requirements-rocm.txt` pins `torch==2.12.1+rocm7.1` from the
  rocm7.1 index
- `requirements/requirements-cpu.txt` pins `torch==2.6.0+cpu` from the CPU
  index

The older `requirements-gpu-minimal.txt` and `requirements-gpu-full.txt`
files no longer exist; if you see references to them, treat them as stale.

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

Prebuilt images carry a backend suffix, for example `v1.6.2-cuda` or
`v1.6.2-rocm`. Moving per-backend tags (`cuda`, `rocm`, `cpu`) track the
latest release of each backend, and `latest` points at the latest CUDA build.

```bash
SERMONPILOT_TAG=v1.6.2-cuda docker compose up -d
```

Each image sets `SERMONPILOT_VARIANT` to its backend and ships a matching
config template: `config/templates/cuda.yaml`, `config/templates/rocm.yaml`,
or `config/templates/cpu.yaml`. The templates differ only in the
transcription section (backend, device, compute type) matched to the image's
hardware stack; the rocm template pins `faster_whisper_local` to CPU and
prefers `whisper_local` on the GPU. The template is optional: import it from
the Settings page (Import/Export) or point `SA_UPDATER_CONFIG` at it to use
it as a file overlay. Container startup prints the variant and the template
path when one exists.

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
- Transcription: `whisper_local` uses the AMD GPU; `faster_whisper_local`
  always runs on CPU (CTranslate2 has no ROCm support), and Clear
  enhancement runs on CPU ONNX Runtime (see above). PyTorch DSP work
  (DeepFilterNet) still uses the GPU.

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

Audio enhancement settings are stored in the SQLite settings database and can
be set from the Settings page in the web UI, seeded from environment variables
(`AUDIO_ENHANCEMENT_METHOD`, `AUDIO_NOISE_REDUCTION`, `AUDIO_NORMALIZE`,
`AUDIO_TARGET_LEVEL`, `AUDIO_GAIN_DB`), or loaded from a file through
`SA_UPDATER_CONFIG`. There is no required config file. The relevant keys:

```yaml
audio_enhancement_method: deepfilternet  # deepfilternet, clear-studio, clear-natural, custom, none
clear_custom_repo: ""                    # Custom Clear model repo (method: custom)
clear_custom_file: ""                    # Custom Clear model file (method: custom)
audio_noise_reduction: true
audio_normalize: true
audio_target_level_db: -22.0
audio_gain_db: 0.5
```

The Clear ONNX model variant follows the method name: `clear-natural` loads
`clear-natural.onnx`, `clear-studio` loads `clear-studio.onnx`.

DeepFilterNet needs PyTorch with CUDA or ROCm support. Clear methods use
ONNX Runtime and work on CUDA or CPU everywhere; on ROCm 7.x they run on CPU
(see the ONNX Runtime note above). Set the enhancement method to `none` to
skip enhancement entirely.

## Troubleshooting

**CUDA is reported as unavailable.** Check the driver and toolkit:

```bash
nvidia-smi
```

Confirm the installed PyTorch build matches the CUDA version of the driver.
Reinstall with the matching wheelhouse from
[step 3](#3-install-gpu-pytorch).

**Out of memory during processing.** Close other GPU applications, reduce
the transcription model size in the transcription settings
(`transcription.faster_whisper_local.model` or `transcription.whisper_local.model`),
or use a smaller enhancement model. Clear ONNX inference generally uses less
memory than DeepFilterNet.

**Faster-whisper runs on CPU even though an AMD GPU is present.** That is
expected: CTranslate2 has no ROCm build, so `src/transcription.py` pins the
faster-whisper device to CPU. Switch the transcription backend to
`whisper_local` to use the AMD GPU (the rocm Docker template does this).

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
