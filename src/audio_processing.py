"""Audio processing for sermon enhancement.

Supports noise reduction, amplification, and normalization with AI models
(DeepFilterNet, Resemble Enhance) and fallback to basic processing.
Includes Q&A audio normalization for automatically adjusting audience question levels.
"""

import logging
import os
import shutil
import sys
import tempfile
import time
import types
import warnings
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any

import numpy as np
import psutil
import soundfile as sf
import torch
import torchaudio
from pydub import AudioSegment

# Import Q&A normalizer
try:
    from .qa_normalizer import QANormalizer
    qa_normalizer_available = True
except ImportError:
    try:
        from qa_normalizer import QANormalizer
        qa_normalizer_available = True
    except ImportError:
        qa_normalizer_available = False
        QANormalizer = None


def peak_normalize(audio_data: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    """
    Normalize audio so the highest peak is at peak_db dBFS.
    """
    peak = np.max(np.abs(audio_data))
    if peak == 0:
        return audio_data
    target_peak = 10 ** (peak_db / 20.0)
    gain = target_peak / peak
    return audio_data * gain

def _ensure_torchaudio_backend_compat():
    """
    DeepFilterNet expects `torchaudio.backend.common.AudioMetaData`, which was
    removed in torchaudio 2.9+.
    """
    try:
        from torchaudio.backend.common import AudioMetaData  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    backend_mod = sys.modules.get("torchaudio.backend")
    if backend_mod is None:
        backend_mod = types.ModuleType("torchaudio.backend")
        sys.modules["torchaudio.backend"] = backend_mod
    common_mod = types.ModuleType("torchaudio.backend.common")
    class AudioMetaData:
        pass
    common_mod.AudioMetaData = AudioMetaData
    backend_mod.common = common_mod
    sys.modules["torchaudio.backend.common"] = common_mod


_ensure_torchaudio_backend_compat()

try:
    from .clear_enhancer import ClearEnhancer
    clear_enhancer_available = True
except ImportError:
    try:
        from clear_enhancer import ClearEnhancer
        clear_enhancer_available = True
    except ImportError:
        clear_enhancer_available = False
        ClearEnhancer = None

try:
    print(f"PyTorch version: {torch.__version__}")
    is_rocm = getattr(torch.version, "hip", None) is not None or \
              "rocm" in (getattr(torch.version, "cuda", "") or "").lower()
    if is_rocm:
        print(f"ROCm available: yes (hip={torch.version.hip})")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")

    from df import enhance, init_df
    print("DeepFilterNet successfully imported via df package")
    deepfilternet_available = True
except ImportError as e:
    print(f"Error importing DeepFilterNet: {e}")
    deepfilternet_available = False
    enhance = None
    init_df = None

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


class AudioProcessor:
    """Advanced audio processor for sermon audio enhancement with multiple AI models."""

    def __init__(self, enhancement_method: str = "deepfilternet", config: dict[str, Any] | None = None):
        """Initialize the audio processor with specified enhancement method.
        
        Note: Models are loaded lazily when first needed to avoid unnecessary 
        initialization during validation-only operations.
        
        Args:
            enhancement_method: AI enhancement method to use
            config: Configuration dictionary for Q&A normalization and other settings
        """
        self.sample_rate = 44100  # Default sample rate
        self.enhancement_method = enhancement_method.lower()
        self.config = config or {}

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_rocm = (
            getattr(torch.version, "hip", None) is not None
            or "rocm" in (getattr(torch.version, "cuda", "") or "").lower()
        )
        if self.device == "cuda":
            if self.is_rocm:
                logger.info("Using AMD GPU (ROCm) for processing")
            else:
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                logger.info(f"Using GPU: {gpu_name} ({gpu_memory:.1f} GB)")
        else:
            logger.info("Using CPU for processing")

        self.df_model = None
        self.df_state = None
        self.clear_enhancer = None
        self._models_initialized = False

        # Q&A normalization support
        self.qa_normalizer = None
        self.qa_processing_enabled = self.config.get('qa_normalization', {}).get('enabled', False)
        if self.qa_processing_enabled and qa_normalizer_available:
            logger.info("Q&A normalization enabled")
        elif self.qa_processing_enabled and not qa_normalizer_available:
            logger.warning("Q&A normalization requested but not available")
            self.qa_processing_enabled = False

        # Validate enhancement method but don't initialize models yet
        if self.enhancement_method not in ["deepfilternet", "clear", "none"]:
            logger.warning(
                f"Unknown enhancement method: {enhancement_method}, "
                f"falling back to deepfilternet"
            )
            self.enhancement_method = "deepfilternet"

        logger.info(f"AudioProcessor initialized with {self.enhancement_method} method (models will load on first use)")

    def _ensure_models_initialized(self):
        """Ensure models are initialized before use. Called lazily on first processing."""
        if self._models_initialized:
            return

        logger.info(f"Initializing {self.enhancement_method} model for audio processing...")

        if self.enhancement_method == "deepfilternet":
            self._init_deepfilternet()
        elif self.enhancement_method == "clear":
            self._init_clear()
        elif self.enhancement_method == "none":
            logger.info("No AI enhancement method selected")

        self._models_initialized = True

    def _init_deepfilternet(self):
        """Initialize DeepFilterNet model."""
        if deepfilternet_available:
            try:
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                logger.info(f"Initializing DeepFilterNet on {device}")

                logger.info("Using legacy df package for DeepFilterNet")

                # Suppress DF initialization logs if not in debug mode
                if logger.level > logging.DEBUG:
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        self.df_model, self.df_state, *_ = init_df()
                else:
                    self.df_model, self.df_state, *_ = init_df()

                logger.info("DeepFilterNet initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize DeepFilterNet: {e}")
                self._fallback_to_basic()
        else:
            logger.error("DeepFilterNet not available")
            self._fallback_to_basic()

    def _init_clear(self):
        """Initialize Clear (desert-ant-labs) enhancer."""
        if clear_enhancer_available:
            try:
                logger.info("Initializing Clear enhancer")
                clear_device = "rocm" if self.is_rocm else self.device
                clear_variant = self.config.get('clear_model_variant', 'natural')
                self.clear_enhancer = ClearEnhancer(device=clear_device, model_variant=clear_variant)
                logger.info("Clear enhancer initialized successfully (variant=%s)", clear_variant)
            except Exception as e:
                logger.error(f"Failed to initialize Clear enhancer: {e}")
                self._fallback_to_basic()
        else:
            logger.error("Clear enhancer not available")
            self._fallback_to_basic()

    def _fallback_to_basic(self):
        """Fallback to basic processing without AI enhancement."""
        logger.warning("Falling back to basic audio processing without AI enhancement")
        self.enhancement_method = "none"

    def load_audio(self, file_path: str) -> tuple[np.ndarray, int]:
        """
        Load audio file and return numpy array and sample rate.

        Args:
            file_path: Path to the audio file

        Returns:
            Tuple of (audio_data, sample_rate)
        """
        logger.info(f"Loading audio from: {file_path}")

        # Try different loading methods
        try:
            # Try soundfile first (handles more formats)
            data, sample_rate = sf.read(file_path)
            logger.info(f"Loaded with soundfile: {data.shape}, SR: {sample_rate}")
            return data, sample_rate
        except Exception as e:
            logger.warning(f"Soundfile failed: {e}, trying pydub...")

        # Fallback to pydub
        try:
            audio = AudioSegment.from_file(file_path)
            # Convert to numpy array
            samples = np.array(audio.get_array_of_samples())

            if audio.channels == 2:
                # Reshape stereo audio
                samples = samples.reshape((-1, 2))
                # Convert to mono by averaging channels
                samples = np.mean(samples, axis=1)

            # Normalize to [-1, 1] range
            orig_dtype = samples.dtype
            samples = samples.astype(np.float32)
            if orig_dtype == np.int16:
                samples = samples / 32768.0
            elif orig_dtype == np.int32:
                samples = samples / 2147483648.0
            elif orig_dtype == np.uint8:
                samples = (samples - 128.0) / 128.0

            return samples, audio.frame_rate
        except Exception as e:
            logger.error(f"Failed to load audio: {e}")
            raise

    def save_audio(self, audio_data: np.ndarray, sample_rate: int, output_path: str):
        """
        Save audio data to file.

        Args:
            audio_data: Numpy array of audio samples
            sample_rate: Sample rate
            output_path: Output file path
        """
        logger.info(f"Saving audio to: {output_path}")

        # Peak normalise to prevent any overshoot
        peak = np.abs(audio_data).max()
        if peak > 1.0:
            audio_data = audio_data / peak

        # Save using soundfile
        sf.write(output_path, audio_data, sample_rate)
        logger.info("Audio saved successfully")

    def custom_noise_reduction(self, audio_data: np.ndarray, sample_rate: int,
                              noise_reduction_amount: float = 0.7) -> np.ndarray:
        """
        Apply custom noise reduction using spectral subtraction.

        Args:
            audio_data: Input audio data
            sample_rate: Sample rate
            noise_reduction_amount: Amount of noise to reduce (0-1)

        Returns:
            Noise-reduced audio data
        """
        logger.info("Applying custom spectral noise reduction")

        # Get noise profile from the first 1 second (or 10% of audio)
        noise_duration = min(1.0, len(audio_data) / sample_rate * 0.1)
        noise_samples = int(noise_duration * sample_rate)
        noise_profile = audio_data[:noise_samples]

        # Smooth the audio first to reduce artifacts
        # (gaussian_filter1d result not used in current implementation)

        # Calculate noise threshold
        noise_rms = np.sqrt(np.mean(noise_profile**2))
        noise_threshold = noise_rms * 2.0

        # Simple spectral subtraction
        # 1. Split audio into chunks
        chunk_size = min(int(sample_rate * 0.2), 4096)  # 200ms chunks
        hop_size = chunk_size // 2
        num_chunks = (len(audio_data) - chunk_size) // hop_size + 1

        # Create output buffer
        output_audio = np.zeros_like(audio_data)
        window = np.hanning(chunk_size)

        # For each chunk
        for i in range(num_chunks):
            start = i * hop_size
            end = start + chunk_size
            if end > len(audio_data):
                break

            # Apply window
            chunk = audio_data[start:end] * window

            # For very quiet parts, reduce the signal
            chunk_rms = np.sqrt(np.mean(chunk**2))
            if chunk_rms < noise_threshold * 1.5:
                reduction_factor = (1.0 - noise_reduction_amount)
                chunk = chunk * reduction_factor

            # Add to output with overlap
            output_audio[start:end] += chunk

        # Normalize for overlapping windows
        normalization = np.zeros_like(audio_data)
        for i in range(num_chunks):
            start = i * hop_size
            end = start + chunk_size
            if end > len(audio_data):
                break
            normalization[start:end] += window

        # Avoid division by zero
        mask = normalization > 0.001
        output_audio[mask] /= normalization[mask]

        # Final noise gate for remaining noise
        gate_threshold = noise_threshold * 0.8
        mask = np.abs(output_audio) < gate_threshold
        output_audio[mask] *= (1.0 - noise_reduction_amount)

        logger.info("Custom noise reduction completed")
        return output_audio

    def get_optimal_chunk_size(self, audio_length: int, sample_rate: int) -> int:
        """
        Dynamically calculate optimal chunk size based on available memory and audio length.

        Args:
            audio_length: Total number of audio samples
            sample_rate: Audio sample rate

        Returns:
            Optimal chunk size in samples
        """
        # Get available memory
        try:
            import psutil
            available_memory_gb = psutil.virtual_memory().available / (1024**3)
        except ImportError:
            available_memory_gb = 8.0  # Default assumption

        if self.device == "cuda" and torch.cuda.is_available():
            gpu_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)

            # Keep processing within VRAM only for optimal performance
            # Shared system memory would significantly slow down GPU processing
            effective_memory_gb = gpu_memory_gb * 0.85  # Use 85% of VRAM to be safe
            logger.info(
                f"Using {effective_memory_gb:.1f}GB of {gpu_memory_gb:.1f}GB VRAM "
                f"(staying within GPU memory for optimal performance)."
            )
        else:
            # Use 60% of available RAM for CPU processing
            effective_memory_gb = available_memory_gb * 0.6

        # Realistic VRAM-only memory usage estimates
        # When staying within VRAM, memory usage is much more efficient
        base_memory_gb = 0.8

        memory_per_minute_gb = 0.35

        # Calculate total VRAM needed
        audio_duration_minutes = audio_length / sample_rate / 60
        estimated_total_memory = base_memory_gb + (audio_duration_minutes * memory_per_minute_gb)

        # Calculate maximum chunk duration based on VRAM constraints
        audio_duration_seconds = audio_length / sample_rate

        # Intelligent chunking optimized for VRAM-only processing
        if estimated_total_memory <= effective_memory_gb:
            # Can fit entire audio in VRAM, but cap for stability
            if audio_duration_seconds <= 1800:  # 30 minutes or less
                max_chunk_seconds = audio_duration_seconds
                logger.info(
                    f"Audio fits in VRAM ({estimated_total_memory:.1f}GB <= "
                    f"{effective_memory_gb:.1f}GB). Processing without chunking."
                )
            else:
                # Use large but stable chunks for longer audio
                max_chunk_seconds = 300  # 5-minute chunks for stability
                logger.info(f"Audio fits in VRAM but using {max_chunk_seconds}-sec chunks for stability (audio: {audio_duration_seconds/60:.0f} min).")
        else:
            # Calculate optimal chunk size that fits in VRAM
            available_for_audio = effective_memory_gb - base_memory_gb
            max_chunk_minutes = available_for_audio / memory_per_minute_gb

            # Cap chunks at reasonable sizes for stability
            max_chunk_seconds = min(max_chunk_minutes * 60, 300)  # Max 5 minutes for stability

            logger.info(f"Using VRAM-optimized chunks: {max_chunk_seconds/60:.1f} minutes per chunk.")

        # Ensure minimum chunk size for quality
        max_chunk_seconds = max(30, max_chunk_seconds)  # At least 30 seconds

        chunk_samples = int(max_chunk_seconds * sample_rate)

        # Don't chunk if entire audio fits in one chunk
        if chunk_samples >= audio_length:
            chunk_samples = audio_length
            logger.info(f"Processing entire {audio_duration_minutes:.1f}-minute audio without chunking (fits in {effective_memory_gb:.1f}GB)")
        else:
            logger.info(f"Dynamic chunking: {max_chunk_seconds:.1f}s chunks ({chunk_samples} samples)")
            logger.info(f"Memory available: {effective_memory_gb:.1f}GB, estimated needed for full audio: {estimated_total_memory:.1f}GB")

        return chunk_samples

    def process_large_audio_in_chunks(self, audio_data: np.ndarray, sample_rate: int,
                                     chunk_size_seconds: float = 30.0) -> np.ndarray:
        """
        Process large audio files in chunks using the selected enhancement method.

        Uses overlap-add between chunks with cross-fade to prevent boundary artifacts.
        Each chunk resets the DeepFilterNet hidden state so state/position
        misalignment cannot accumulate.

        Args:
            audio_data: Input audio data
            sample_rate: Sample rate
            chunk_size_seconds: Size of each chunk in seconds

        Returns:
            Processed audio data
        """

        # Monitor memory before chunking
        if torch.cuda.is_available():
            gpu_memory_before = torch.cuda.memory_allocated(0) / (1024**3)
            gpu_reserved_before = torch.cuda.memory_reserved(0) / (1024**3)
        else:
            gpu_memory_before = 0.0
            gpu_reserved_before = 0.0
        system_memory_before = psutil.virtual_memory().used / (1024**3)

        logger.info(f"🔍 MEMORY BEFORE CHUNKING: GPU {gpu_memory_before:.1f}GB allocated, {gpu_reserved_before:.1f}GB reserved, System {system_memory_before:.1f}GB used")

        chunk_start_time = time.time()

        # Calculate chunk size in samples
        chunk_size = int(chunk_size_seconds * sample_rate)
        overlap_samples = int(chunk_size * 0.1)  # 10% overlap for cross-fade
        hop_size = chunk_size - overlap_samples

        # Calculate number of chunks
        num_chunks = (len(audio_data) + hop_size - 1) // hop_size

        # Process each chunk with overlap-add
        # Each chunk resets DeepFilterNet hidden state for clean processing,
        # then results are stitched with cross-fade overlap-add.
        output_audio = np.zeros(len(audio_data), dtype=np.float64)
        window_sum = np.zeros(len(audio_data), dtype=np.float64)

        # Hann window for cross-fade
        fade_in = np.sin(np.pi * np.arange(overlap_samples) / (2 * overlap_samples)) ** 2
        fade_out = np.sin(np.pi * (np.arange(overlap_samples) + overlap_samples) / (2 * overlap_samples)) ** 2

        for i in range(num_chunks):
            start = i * hop_size
            end = min(start + chunk_size, len(audio_data))
            chunk = audio_data[start:end]

            orig_len = end - start
            individual_chunk_start = time.time()
            logger.info(f"Processing chunk {i+1}/{num_chunks} with {self.enhancement_method}")

            try:
                if self.enhancement_method == "deepfilternet":
                    processed_chunk = self._process_chunk_deepfilternet(chunk)
                else:
                    processed_chunk = chunk if chunk.ndim == 1 else chunk[0]

                individual_chunk_end = time.time()
                chunk_duration = (end - start) / sample_rate
                processing_time = individual_chunk_end - individual_chunk_start
                speed_factor = chunk_duration / processing_time
                logger.info(
                    f"⏱️  Chunk {i+1}: {processing_time:.1f}s to process "
                    f"{chunk_duration:.1f}s audio (speed: {speed_factor:.1f}x realtime)"
                )

                # Ensure output length matches input chunk
                proc_len = len(processed_chunk)
                if proc_len < orig_len:
                    logger.warning(f"Processed chunk shorter than input: input {orig_len}, output {proc_len}. Padding with zeros.")
                    padded = np.zeros(orig_len, dtype=processed_chunk.dtype)
                    padded[:proc_len] = processed_chunk
                    processed_chunk = padded
                elif proc_len > orig_len:
                    logger.warning(f"Processed chunk longer than input: input {orig_len}, output {proc_len}. Trimming.")
                    processed_chunk = processed_chunk[:orig_len]

                # Peak normalisation per chunk instead of hard clip
                peak = np.abs(processed_chunk).max()
                if peak > 1.0:
                    processed_chunk = processed_chunk / peak

                # Apply cross-fade in overlap region
                chunk_window = np.ones(orig_len)
                if i > 0 and overlap_samples > 0:
                    chunk_window[:overlap_samples] = fade_in
                if end < len(audio_data) and overlap_samples > 0:
                    chunk_window[-overlap_samples:] = fade_out

                output_audio[start:end] += processed_chunk * chunk_window
                window_sum[start:end] += chunk_window

            except Exception as e:
                logger.error(f"Error processing chunk {i+1}: {e}")
                chunk_window = np.ones(orig_len)
                if i > 0 and overlap_samples > 0:
                    chunk_window[:overlap_samples] = fade_in
                if end < len(audio_data) and overlap_samples > 0:
                    chunk_window[-overlap_samples:] = fade_out
                output_audio[start:end] += (chunk if chunk.ndim == 1 else chunk[0]) * chunk_window
                window_sum[start:end] += chunk_window

        # Normalize by window sum to avoid amplitude modulation
        window_sum = np.maximum(window_sum, 1e-10)
        output_audio = output_audio / window_sum
        peak = np.abs(output_audio).max()
        if peak > 1.0:
            output_audio = output_audio / peak
        output_audio = output_audio.astype(np.float32)

        # Monitor memory after chunking
        if torch.cuda.is_available():
            gpu_memory_after = torch.cuda.memory_allocated(0) / (1024**3)
            gpu_reserved_after = torch.cuda.memory_reserved(0) / (1024**3)
        else:
            gpu_memory_after = 0.0
            gpu_reserved_after = 0.0
        system_memory_after = psutil.virtual_memory().used / (1024**3)

        chunk_end_time = time.time()
        total_chunk_time = chunk_end_time - chunk_start_time

        logger.info(
            f"🔍 MEMORY AFTER CHUNKING: GPU {gpu_memory_after:.1f}GB allocated "
            f"({gpu_memory_after-gpu_memory_before:+.1f}GB), "
            f"{gpu_reserved_after:.1f}GB reserved "
            f"({gpu_reserved_after-gpu_reserved_before:+.1f}GB)"
        )
        logger.info(f"🔍 SYSTEM MEMORY: {system_memory_after:.1f}GB used ({system_memory_after-system_memory_before:+.1f}GB change)")
        logger.info(f"⏱️  CHUNK PROCESSING TIME: {total_chunk_time:.1f}s for {num_chunks} chunks ({total_chunk_time/num_chunks:.1f}s per chunk)")

        logger.warning("AI chunked processing may cause artifacts at chunk boundaries. For best quality, try processing the whole file if memory allows.")
        return output_audio

    def _process_chunk_deepfilternet(self, chunk: np.ndarray) -> np.ndarray:
        """Process a single 48 kHz chunk with DeepFilterNet.

        Assumes audio is already at 48 kHz. Resets model hidden state per chunk
        and applies peak normalisation instead of hard-clipping.
        """
        if chunk.dtype != np.float32:
            chunk = chunk.astype(np.float32)
        if chunk.ndim == 1:
            chunk = chunk[np.newaxis, :]

        # Reset model hidden state so each chunk starts fresh
        device = next(self.df_model.parameters()).device
        bs = 1
        if hasattr(self.df_model, "reset_h0"):
            self.df_model.reset_h0(batch_size=bs, device=device)
        elif hasattr(self.df_model, "df") and hasattr(self.df_model.df, "reset_h0"):
            self.df_model.df.reset_h0(batch_size=bs, device=device)

        chunk_tensor = torch.from_numpy(chunk).contiguous()
        processed_tensor = enhance(self.df_model, self.df_state, chunk_tensor)
        if isinstance(processed_tensor, torch.Tensor):
            processed_chunk = processed_tensor.cpu().numpy()
        else:
            processed_chunk = processed_tensor
        if processed_chunk.ndim == 2 and processed_chunk.shape[0] == 1:
            processed_chunk = processed_chunk[0]

        # Peak normalisation instead of hard clipping
        peak = np.abs(processed_chunk).max()
        if peak > 1.0:
            processed_chunk = processed_chunk / peak

        return processed_chunk

    def apply_noise_reduction(self, audio_data: np.ndarray, sample_rate: int,
                            stationary: bool = True, prop_decrease: float = 1.0,
                            skip_large_files: bool = False,
                            size_threshold: int = None) -> np.ndarray:
        """
        Apply AI-based noise reduction using the configured enhancement method.
        Process large files in chunks to avoid memory issues.

        Args:
            audio_data: Input audio data
            sample_rate: Sample rate
            stationary: Whether to use stationary noise reduction (unused)
            prop_decrease: Proportion of noise to reduce (unused)
            skip_large_files: Whether to skip large files (unused)
            size_threshold: Size threshold in samples for chunk processing (auto-detected if None)

        Returns:
            Noise-reduced audio data
        """
        # Ensure audio is float32
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        self._ensure_models_initialized()

        logger.info(f"Processing audio with {self.enhancement_method} (length: {len(audio_data)} samples)")

        # Route based on enhancement method
        if self.enhancement_method == "deepfilternet":
            return self._apply_deepfilternet(audio_data, sample_rate, size_threshold)
        elif self.enhancement_method == "clear":
            return self._apply_clear(audio_data, sample_rate)
        elif self.enhancement_method == "none":
            logger.info("No enhancement requested, returning original audio")
            return audio_data
        else:
            logger.warning(f"Unknown enhancement method: {self.enhancement_method}, falling back to no enhancement")
            return audio_data

    def _pre_process_audio(self, audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
        """Pre-process audio before DeepFilterNet: noise gate, gentle limiter.

        Mirrors the Audacity "Sermon Edit" macro pattern minimally — reduces
        low-level noise and tames hard peaks without boosting overall level.
        DeepFilterNet handles noise suppression; over-boosting here causes staticky
        peaks.
        """
        data = audio_data.astype(np.float64)

        rms = np.sqrt(np.mean(data ** 2))
        if rms == 0:
            return audio_data

        # 1 — Noise gate: reduce quiet sections by 12 dB
        gate_threshold = rms * 0.08
        gate_mask = np.abs(data) < gate_threshold
        data[gate_mask] *= 0.25

        # 2 — Gentle peak reduction: only clamp extreme outliers above -3 dBFS
        limit = 10 ** (-3.0 / 20.0)
        peak = np.abs(data).max()
        if peak > limit:
            data = data * (limit / peak)

        return data.astype(np.float32)

    def _apply_deepfilternet(self, audio_data: np.ndarray, sample_rate: int, size_threshold: int = None) -> np.ndarray:
        """Apply DeepFilterNet noise reduction.

        Resamples the entire audio to 48 kHz upfront (DeepFilterNet's native
        rate), processes at that rate, then resamples back — matching the
        clean-audio.py approach.
        """
        start_time = time.time()
        original_sample_rate = sample_rate

        logger.info(f"Processing audio with DeepFilterNet (length: {len(audio_data)} samples, sr={sample_rate} Hz)")

        # Pre-process: noise gate, gentle limiting
        logger.info("Pre-processing audio before DeepFilterNet (noise gate, limiting)")
        audio_data = self._pre_process_audio(audio_data, sample_rate)

        # Resample entire audio to 48 kHz — DeepFilterNet's native rate
        if sample_rate != 48000:
            logger.info(f"Resampling from {sample_rate} Hz to 48000 Hz for DeepFilterNet")
            audio_t = torch.from_numpy(audio_data.astype(np.float32)).contiguous()
            if audio_t.ndim == 1:
                audio_t = audio_t.unsqueeze(0)
            audio_t = torchaudio.functional.resample(audio_t, sample_rate, 48000)
            audio_data = audio_t.squeeze(0).numpy() if audio_t.shape[0] == 1 else audio_t.numpy()
            if audio_data.ndim == 1 and audio_data.shape[0] == 1:
                audio_data = audio_data[0]
            sample_rate = 48000
            logger.info(f"Resampled to {sample_rate} Hz, length: {len(audio_data)} samples")

        try:
            # Use dynamic chunk size based on available memory
            optimal_chunk_samples = self.get_optimal_chunk_size(len(audio_data), sample_rate)
            optimal_chunk_seconds = optimal_chunk_samples / sample_rate

            if size_threshold is None or size_threshold > optimal_chunk_samples:
                size_threshold = optimal_chunk_samples
                logger.info(f"Set DeepFilterNet chunking threshold to {size_threshold} samples (dynamic {optimal_chunk_seconds:.1f}s chunks)")
            # Process in chunks if file is large
            if len(audio_data) > size_threshold:
                logger.info("Large audio file detected, processing in chunks")
                chunk_start_time = time.time()
                result = self.process_large_audio_in_chunks(audio_data, sample_rate, chunk_size_seconds=optimal_chunk_seconds)
                chunk_end_time = time.time()
                total_time = chunk_end_time - start_time
                chunk_time = chunk_end_time - chunk_start_time
                logger.info(f"⏱️  CHUNKED PROCESSING: Total time {total_time:.1f}s, Chunking overhead: {total_time - chunk_time:.1f}s")
            else:
                # Process normally for smaller files
                logger.info("Using DeepFilterNet for noise reduction")
                was_1d = audio_data.ndim == 1
                if was_1d:
                    audio_data_2d = audio_data[np.newaxis, :]
                else:
                    audio_data_2d = audio_data
                # Reset h0 for single-pass processing
                device = next(self.df_model.parameters()).device
                if hasattr(self.df_model, "reset_h0"):
                    self.df_model.reset_h0(batch_size=1, device=device)
                elif hasattr(self.df_model, "df") and hasattr(self.df_model.df, "reset_h0"):
                    self.df_model.df.reset_h0(batch_size=1, device=device)
                audio_tensor = torch.from_numpy(audio_data_2d).contiguous()
                processed_tensor = enhance(self.df_model, self.df_state, audio_tensor)
                if isinstance(processed_tensor, torch.Tensor):
                    result = processed_tensor.cpu().numpy()
                else:
                    result = processed_tensor
                if result.ndim == 2 and result.shape[0] == 1:
                    result = result[0]

            # Resample result back to original sample rate
            if original_sample_rate != 48000:
                logger.info(f"Resampling result from 48000 Hz back to {original_sample_rate} Hz")
                res_t = torch.from_numpy(result.astype(np.float32)).contiguous()
                if res_t.ndim == 1:
                    res_t = res_t.unsqueeze(0)
                res_t = torchaudio.functional.resample(res_t, 48000, original_sample_rate)
                result = res_t.squeeze(0).numpy() if res_t.shape[0] == 1 else res_t.numpy()
                if result.ndim == 1 and result.shape[0] == 1:
                    result = result[0]

            # Peak normalisation
            peak = np.abs(result).max()
            if peak > 1.0:
                result = result / peak
            logger.info("DeepFilterNet noise reduction completed successfully")
            return result
        except Exception as e:
            logger.error(f"DeepFilterNet processing failed: {e}")
            audio_for_fallback = audio_data
            if sample_rate != original_sample_rate:
                res_t = torch.from_numpy(audio_data.astype(np.float32)).contiguous()
                if res_t.ndim == 1:
                    res_t = res_t.unsqueeze(0)
                res_t = torchaudio.functional.resample(res_t, 48000, original_sample_rate)
                audio_for_fallback = res_t.squeeze(0).numpy() if res_t.shape[0] == 1 else res_t.numpy()
            try:
                logger.info("Retrying DeepFilterNet with chunked processing")
                chunk_seconds = 30
                return self.process_large_audio_in_chunks(
                    audio_for_fallback, original_sample_rate, chunk_size_seconds=chunk_seconds
                )
            except Exception as e2:
                logger.error(f"DeepFilterNet chunked processing also failed: {e2}")
                logger.warning("Falling back to custom noise reduction")
                return self.custom_noise_reduction(audio_for_fallback if audio_for_fallback.ndim == 1 else audio_for_fallback[0], original_sample_rate, noise_reduction_amount=0.7)

    def _apply_clear(self, audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
        """Apply Clear (desert-ant-labs) noise suppression."""
        start_time = time.time()
        logger.info("Processing audio with Clear enhancer")
        result = self.clear_enhancer.enhance(audio_data, sample_rate)
        elapsed = time.time() - start_time
        logger.info("Clear enhancement completed in %.1fs", elapsed)
        return result

    def amplify_audio(self, audio_data: np.ndarray, gain_db: float = 3.0) -> np.ndarray:
        """
        Amplify audio by specified gain in dB.

        Args:
            audio_data: Input audio data
            gain_db: Gain in decibels

        Returns:
            Amplified audio data
        """
        logger.info(f"Amplifying audio by {gain_db} dB")

        # Convert dB to linear gain
        gain_linear = 10 ** (gain_db / 20.0)

        # Apply gain
        amplified = audio_data * gain_linear

        # Peak normalise instead of hard clip
        peak = np.abs(amplified).max()
        if peak > 1.0:
            amplified = amplified / peak

        return amplified

    def normalize_audio(self, audio_data: np.ndarray, target_level: float = -25.0) -> np.ndarray:
        """
        Normalize audio to target level using RMS normalization.

        Args:
            audio_data: Input audio data
            target_level: Target RMS level in dB

        Returns:
            Normalized audio data
        """
        logger.info(f"Normalizing audio to {target_level} dB")

        # Calculate current RMS level
        rms = np.sqrt(np.mean(audio_data ** 2))

        # Avoid log of zero
        if rms == 0:
            return audio_data

        current_db = 20 * np.log10(rms)

        # Calculate gain needed
        gain_db = target_level - current_db

        # Apply gain
        return self.amplify_audio(audio_data, gain_db)



    def process_sermon_audio(self, input_path: str, output_path: str,
                           noise_reduction: bool = True,
                           amplify: bool = True,
                           normalize: bool = True,
                           gain_db: float = 0.0,
                           target_level_db: float = -22.0,
                           max_duration_minutes: int | None = None,
                           apply_qa_normalization: bool = None) -> tuple[bool, dict[str, Any] | None]:
        """
        Complete sermon audio processing pipeline with safeguards for large files and Q&A normalization.

        Args:
            input_path: Input audio file path
            output_path: Output audio file path
            noise_reduction: Apply noise reduction
            amplify: Apply amplification
            normalize: Apply normalization
            gain_db: Amplification gain in dB
            target_level_db: Target normalization level in dB
            max_duration_minutes: Maximum duration to process in minutes (None for no limit)
            apply_qa_normalization: Whether to apply Q&A normalization (None = use config setting)

        Returns:
            Tuple of (success_status, qa_processing_info)
        """
        # Ensure models are initialized before processing
        self._ensure_models_initialized()

        # Initialize Q&A processing info
        qa_processing_info = None

        # Determine if Q&A normalization should be applied
        should_apply_qa = apply_qa_normalization
        if should_apply_qa is None:
            should_apply_qa = self.qa_processing_enabled

        try:
            # Load audio
            audio_data, sample_rate = self.load_audio(input_path)
            # Calculate duration
            duration_seconds = len(audio_data) / sample_rate
            duration_minutes = duration_seconds / 60
            logger.info(f"Audio loaded: {len(audio_data)} samples at {sample_rate} Hz ({duration_minutes:.2f} minutes)")

            # Safety check for extremely long files (disabled if max_duration_minutes is None)
            if max_duration_minutes is not None and duration_minutes > max_duration_minutes:
                logger.warning(f"Audio exceeds maximum duration of {max_duration_minutes} minutes. Processing first {max_duration_minutes} minutes only.")
                max_samples = int(max_duration_minutes * 60 * sample_rate)
                audio_data = audio_data[:max_samples]

            # Step 1: Q&A normalization (before other processing)
            if should_apply_qa and qa_normalizer_available:
                try:
                    logger.info("Applying Q&A normalization")
                    if self.qa_normalizer is None:
                        self.qa_normalizer = QANormalizer(self.config)

                    # Create temporary file for Q&A processing
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                        temp_path = temp_file.name

                    # Save current audio for Q&A processing
                    sf.write(temp_path, audio_data, sample_rate)

                    # Apply Q&A normalization
                    normalized_audio, _ = self.qa_normalizer.process_audio(temp_path)
                    audio_data = normalized_audio

                    # Get processing statistics
                    qa_processing_info = self.qa_normalizer.get_processing_stats()
                    qa_processing_info['qa_segments'] = self.qa_normalizer.get_segments()

                    # Clean up temporary file
                    os.unlink(temp_path)

                    logger.info(f"Q&A normalization applied: {len(qa_processing_info.get('qa_segments', []))} segments processed")
                except Exception as e:
                    logger.warning(f"Q&A normalization failed: {e}")
                    qa_processing_info = {'error': str(e), 'qa_segments': []}
            elif should_apply_qa and not qa_normalizer_available:
                logger.warning("Q&A normalization requested but not available")
                qa_processing_info = {'error': 'Q&A normalizer not available', 'qa_segments': []}

            # Step 2: Apply noise reduction if requested
            if noise_reduction:
                audio_data = self.apply_noise_reduction(audio_data, sample_rate)
            # Peak normalise instead of hard clip after noise reduction
            peak = np.abs(audio_data).max()
            if peak > 1.0:
                audio_data = audio_data / peak

            # Step 3: Apply amplification or normalization, not both
            if normalize:
                audio_data = self.normalize_audio(audio_data, target_level_db)
            elif amplify:
                audio_data = self.amplify_audio(audio_data, gain_db)

            # Step 4: Final peak normalization before saving
            audio_data = peak_normalize(audio_data, peak_db=-1.0)

            # Step 5: Save processed audio
            self.save_audio(audio_data, sample_rate, output_path)
            logger.info("Audio processing completed successfully")
            return True, qa_processing_info
        except Exception as e:
            logger.error(f"Audio processing failed: {e}")
            return False, qa_processing_info



# Audacity command-line interface (alternative approach)
class AudacityProcessor:
    def __init__(self, use_pipe=True):
        self.use_pipe = use_pipe
        self.pipe_exists = False
        if use_pipe:
            self._check_pipe()

    def _check_pipe(self):
        """Check if Audacity pipe is available."""
        if os.name == 'nt':  # Windows
            self.toname = '\\.pipe\\ToSrvPipe'
            self.fromname = '\\.pipe\\FromSrvPipe'
        else:  # Linux/Mac
            self.toname = '/tmp/audacity_script_pipe.to.' + str(os.getuid())
            self.fromname = '/tmp/audacity_script_pipe.from.' + str(os.getuid())
        self.pipe_exists = os.path.exists(self.toname) and os.path.exists(self.fromname)
        if self.pipe_exists:
            logger.info("Audacity pipe detected")
        else:
            logger.warning("Audacity pipe not found. Make sure Audacity is running with mod-script-pipe enabled")

    def send_command(self, command: str) -> str | None:
        """Send command to Audacity via pipe."""
        if not self.pipe_exists:
            return None
        try:
            # Write command
            with open(self.toname, 'w') as tofile:
                tofile.write(command + ('\r\n\0' if os.name == 'nt' else '\n'))
                tofile.flush()
            # Read response
            result = ''
            with open(self.fromname) as fromfile:
                while True:
                    line = fromfile.readline()
                    if line == '\n' and len(result) > 0:
                        break
                    result += line
            return result
        except Exception as e:
            logger.error(f"Pipe command failed: {e}")
            return None

    def process_with_macro(self, input_path: str, output_path: str, macro_name: str = "Sermon Edit") -> bool:
        """
        Process audio using Audacity macro.
        Args:
            input_path: Input audio file
            output_path: Output audio file
            macro_name: Name of Audacity macro to apply
        Returns:
            Success status
        """
        if not self.pipe_exists:
            logger.error("Audacity pipe not available")
            return False
        try:
            # Import audio
            self.send_command(f'Import2: Filename="{input_path}"')
            # Select all
            self.send_command('SelectAll')
            # Apply macro
            self.send_command(f'ApplyMacro: MacroName="{macro_name}"')
            # Export
            self.send_command(f'Export2: Filename="{output_path}" NumChannels=1')
            # Close
            self.send_command('Close')
            return True
        except Exception as e:
            logger.error(f"Audacity processing failed: {e}")
            return False


# Convenience function
def process_sermon_audio(input_path: str, output_path: str, use_audacity: bool = False,
                       skip_on_error: bool = True, enhancement_method: str = "deepfilternet",
                       verbose: bool = False, config: dict[str, Any] | None = None, **kwargs) -> tuple[bool, dict[str, Any] | None]:
    """
    Process sermon audio with selected enhancement method.

    Args:
        input_path: Input audio file
        output_path: Output audio file
        use_audacity: Use Audacity if True, else use native Python processing
        enhancement_method: AI enhancement method to use ("deepfilternet", "clear", "none")
        verbose: Show detailed processing information
        config: Configuration dictionary for Q&A normalization and other settings
        **kwargs: Additional arguments for processing

    Returns:
        Tuple of (success_status, qa_processing_info)
    """
    if use_audacity:
        processor = AudacityProcessor()
        if processor.pipe_exists:
            success = processor.process_with_macro(input_path, output_path)
            return success, None  # Audacity doesn't provide Q&A info
        else:
            logger.warning(f"Audacity not available, using {enhancement_method} processing")

    # Use AI enhancement processing
    try:
        # Suppress DF logs if not in verbose mode
        if not verbose and enhancement_method.lower() == "deepfilternet":
            # Completely suppress DF output
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                processor = AudioProcessor(enhancement_method=enhancement_method, config=config)
                result, qa_info = processor.process_sermon_audio(input_path, output_path, **kwargs)
            return result, qa_info
        else:
            processor = AudioProcessor(enhancement_method=enhancement_method, config=config)
            if verbose:
                logger.info(f"Processing with {enhancement_method}")
            return processor.process_sermon_audio(input_path, output_path, **kwargs)
    except Exception as e:
        logger.error(f"Audio processing failed with error: {e}")
        if skip_on_error:
            # If we can't process, just copy the original file
            logger.warning(f"{enhancement_method} processing failed, copying original file")
            try:
                import shutil
                shutil.copy2(input_path, output_path)
                return True, None
            except Exception as copy_error:
                logger.error(f"Failed to copy original file: {copy_error}")
                return False, None
        else:
            # Re-raise the exception if skip_on_error is False
            raise
