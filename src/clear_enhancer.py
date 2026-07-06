"""Clear noise suppression using desert-ant-labs/clear ONNX model.

Built on DeepFilterNet 3 architecture, fine-tuned on a speech corpus.
Runs via ONNX Runtime — no PyTorch dependency for inference.
Supports CUDA, ROCm, and CPU execution providers.
"""

import logging
import os
import sys
import time
import types
from pathlib import Path

import numpy as np
import torch
import torchaudio

# DeepFilterNet's io.py imports torchaudio.backend.common.AudioMetaData
# which was removed in torchaudio 2.9+. Provide a compat shim.
try:
    from torchaudio.backend.common import AudioMetaData  # noqa: F401
except ModuleNotFoundError:
    backend_mod = types.ModuleType("torchaudio.backend")
    sys.modules["torchaudio.backend"] = backend_mod
    common_mod = types.ModuleType("torchaudio.backend.common")
    class AudioMetaData:
        pass
    common_mod.AudioMetaData = AudioMetaData
    backend_mod.common = common_mod
    sys.modules["torchaudio.backend.common"] = common_mod

logger = logging.getLogger(__name__)

CLEAR_MODEL_REPO = "desert-ant-labs/clear"
CLEAR_MODEL_FILE = "clear-studio.onnx"
CLEAR_SAMPLE_RATE = 48000
CHUNK_FRAMES = 200


class ClearEnhancer:
    def __init__(self, device: str = "cpu"):
        self.device = device
        self._session = None
        self._df_model = None
        self._df_state = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        self._init_onnx_session()
        self._init_df_dsp()
        self._initialized = True

    def _init_onnx_session(self):
        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError(
                "onnxruntime is required for Clear enhancement. "
                "Install with: pip install onnxruntime"
            )

        from huggingface_hub import hf_hub_download

        model_path = hf_hub_download(CLEAR_MODEL_REPO, CLEAR_MODEL_FILE)
        logger.info("Clear ONNX model downloaded to %s", model_path)

        requested = self._get_ort_providers()
        available = ort.get_available_providers()
        providers = [p for p in requested if p in available]
        if providers != requested:
            skipped = [p for p in requested if p not in available]
            # When on ROCm, the ROCM provider not being available is expected
            # (the only pip wheel is built against ROCm 6.4.2 ABI, incompatible
            # with ROCm 7.x systems). Demote to info to avoid log noise.
            if self.device == "rocm" and "ROCMExecutionProvider" in skipped:
                logger.info(
                    "Clear: ROCM provider unavailable on this system "
                    "(onnxruntime-rocm pip wheel is built for ROCm 6.4.2 ABI). "
                    "Falling back to CPU ORT — still ~80x realtime."
                )
            else:
                logger.warning(
                    "Clear: requested ORT providers %s but only %s are available; "
                    "falling back. Missing: %s",
                    requested, available, skipped
                )
        self._session = ort.InferenceSession(model_path, providers=providers)
        logger.info("Clear ONNX session created with providers=%s", providers)

    def _get_ort_providers(self):
        if self.device == "cuda":
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        elif self.device == "rocm":
            return ["ROCMExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def _init_df_dsp(self):
        from df.enhance import init_df, df_features

        self._df_model, self._df_state, *_ = init_df()
        self._df_features_fn = df_features
        # Force CPU for DF DSP — we only need STFT/ERB feature extraction
        # (small tensors), and the ORT session is what does the heavy lifting
        # on the GPU. Avoiding CUDA tensors here sidesteps a torch<->numpy
        # round-trip issue in df.enhance.df_features.
        self._device = "cpu"
        self._n_fft = self._df_state.fft_size()
        self._hop = self._df_state.hop_size()
        self._nb_df = getattr(
            self._df_model, "nb_df",
            getattr(self._df_model, "df_bins", 32)
        )
        logger.info("DF DSP initialized: n_fft=%d, hop=%d, device=%s", self._n_fft, self._hop, self._device)

    def enhance(self, audio: np.ndarray, sr: int) -> np.ndarray:
        self._ensure_initialized()

        original_sr = sr
        if sr != CLEAR_SAMPLE_RATE:
            audio_t = torch.from_numpy(audio.astype(np.float32))
            if audio_t.ndim == 1:
                audio_t = audio_t.unsqueeze(0)
            audio_t = torchaudio.functional.resample(audio_t, sr, CLEAR_SAMPLE_RATE)
            audio = audio_t.squeeze(0).numpy()
            sr = CLEAR_SAMPLE_RATE
            logger.info("Clear: resampled %d Hz -> %d Hz (%d -> %d samples)",
                        original_sr, sr, len(audio), len(audio))
        was_1d = audio.ndim == 1
        if was_1d:
            audio = audio[np.newaxis, :]

        audio_t = torch.from_numpy(audio.astype(np.float32)).to(self._device)
        audio_t = torch.nn.functional.pad(audio_t, (0, self._n_fft))

        spec, erb_feat, spec_feat = self._df_features_fn(
            audio_t, self._df_state, self._nb_df, device=self._device
        )

        n_frames = spec.shape[2]
        enhanced_frames = []

        for start in range(0, n_frames, CHUNK_FRAMES):
            end = min(start + CHUNK_FRAMES, n_frames)
            spec_chunk = spec[:, :, start:end].cpu().numpy().astype(np.float32)
            erb_chunk = erb_feat[:, :, start:end].cpu().numpy().astype(np.float32)
            spec_feat_chunk = spec_feat[:, :, start:end].cpu().numpy().astype(np.float32)

            if spec_chunk.shape[2] < CHUNK_FRAMES:
                pad = CHUNK_FRAMES - spec_chunk.shape[2]
                spec_chunk = np.pad(spec_chunk, ((0,0),(0,0),(0,pad),(0,0),(0,0)))
                erb_chunk = np.pad(erb_chunk, ((0,0),(0,0),(0,pad),(0,0)))
                spec_feat_chunk = np.pad(spec_feat_chunk, ((0,0),(0,0),(0,pad),(0,0),(0,0)))

            out = self._session.run(None, {
                "spec": spec_chunk,
                "feat_erb": erb_chunk,
                "feat_spec": spec_feat_chunk,
            })
            result = torch.from_numpy(out[0])
            if spec_chunk.shape[2] > end - start:
                result = result[:, :, :end - start]
            enhanced_frames.append(result)

        spec_enhanced = torch.cat(enhanced_frames, dim=2)

        from df.enhance import as_complex
        enhanced_complex = as_complex(spec_enhanced.squeeze(1))
        audio_out = torch.as_tensor(self._df_state.synthesis(enhanced_complex.numpy()))
        d = self._n_fft - self._hop
        audio_out = audio_out[..., d:-d]

        result = audio_out.cpu().numpy()
        if was_1d:
            result = result[0]

        # Resample back to the original sample rate to keep duration unchanged
        if original_sr != CLEAR_SAMPLE_RATE:
            result_t = torch.from_numpy(result.astype(np.float32))
            if result_t.ndim == 1:
                result_t = result_t.unsqueeze(0)
            result_t = torchaudio.functional.resample(result_t, CLEAR_SAMPLE_RATE, original_sr)
            result = result_t.squeeze(0).numpy()
            if result.ndim == 1 and result.shape[0] == 1:
                result = result[0]
            logger.info("Clear: resampled back %d Hz -> %d Hz (%d samples, %.2fs)",
                        CLEAR_SAMPLE_RATE, original_sr, len(result), len(result) / original_sr)

        peak = np.abs(result).max()
        if peak > 1.0:
            result = result / peak

        return result
