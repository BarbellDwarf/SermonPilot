"""Audio processing for sermon enhancement.

Supports noise reduction, amplification, and normalization with AI models
(DeepFilterNet, Resemble Enhance) and fallback to basic processing.
"""

import logging
import os
import shutil
import tempfile
import time
import warnings
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import numpy as np
import psutil
import soundfile as sf
import torch
from pydub import AudioSegment


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

try:
    print(f"PyTorch version: {torch.__version__}")
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

try:
    from resemble_enhance.enhancer.inference import denoise
    print("Resemble Enhance Python API successfully imported")
    resemble_enhance_available = True
    resemble_enhance_mode = "python_api"
except ImportError as e:
    print(f"Resemble Enhance Python API not available: {e}")
    try:
        resemble_enhance_cmd = shutil.which("resemble-enhance")
        if resemble_enhance_cmd:
            print("Resemble Enhance command line tool found")
            resemble_enhance_available = True
            resemble_enhance_mode = "command_line"
        else:
            print("Resemble Enhance command line tool not found")
            resemble_enhance_available = False
            resemble_enhance_mode = None
    except Exception as e2:
        print(f"Error checking for Resemble Enhance: {e2}")
        resemble_enhance_available = False
        resemble_enhance_mode = None

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


class AudioProcessor:
    """Advanced audio processor for sermon audio enhancement with multiple AI models."""

    def __init__(self, enhancement_method: str = "resemble_enhance"):
        """Initialize the audio processor with specified enhancement method."""
        self.sample_rate = 44100  # Default sample rate
        self.enhancement_method = enhancement_method.lower()

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            logger.info(f"Using GPU: {gpu_name} ({gpu_memory:.1f} GB)")
        else:
            logger.info("Using CPU for processing")

        self.df_model = None
        self.df_state = None
        self.resemble_model = None

        if self.enhancement_method == "deepfilternet":
            self._init_deepfilternet()
        elif self.enhancement_method == "resemble_enhance":
            self._init_resemble_enhance()
        elif self.enhancement_method == "none":
            logger.info("No AI enhancement method selected")
        else:
            logger.warning(
                f"Unknown enhancement method: {enhancement_method}, "
                f"falling back to DeepFilterNet"
            )
            self._init_deepfilternet()

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
                        self.df_model, self.df_state, _ = init_df()
                else:
                    self.df_model, self.df_state, _ = init_df()
                    
                logger.info("DeepFilterNet initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize DeepFilterNet: {e}")
                self._fallback_to_basic()
        else:
            logger.error("DeepFilterNet not available")
            self._fallback_to_basic()

    def _init_resemble_enhance(self):
        """Initialize Resemble Enhance model."""
        if resemble_enhance_available:
            try:
                logger.info("Initializing Resemble Enhance")
                logger.info("Resemble Enhance ready")
            except Exception as e:
                logger.error(f"Failed to initialize Resemble Enhance: {e}")
                logger.info("Falling back to DeepFilterNet")
                self._init_deepfilternet()
        else:
            logger.error("Resemble Enhance not available, falling back to DeepFilterNet")
            self._init_deepfilternet()

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
            samples = samples.astype(np.float32)
            if samples.dtype == np.int16:
                samples = samples / 32768.0
            elif samples.dtype == np.int32:
                samples = samples / 2147483648.0

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

        # Ensure audio is in the correct range
        audio_data = np.clip(audio_data, -1.0, 1.0)

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
        base_memory_gb = 0.8  # Model + PyTorch + DeepFilterNet overhead

        if self.enhancement_method == "resemble_enhance":
            memory_per_minute_gb = 0.25  # More memory intensive, increased estimate
        else:  # DeepFilterNet or others
            memory_per_minute_gb = 0.10  # Empirical: ~100MB per minute within VRAM

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
                if self.enhancement_method == "resemble_enhance":
                    max_chunk_seconds = 180  # 3-minute chunks for Resemble Enhance stability
                    logger.info(
                        f"Audio fits in VRAM but using 3-min chunks for "
                        f"Resemble Enhance stability (audio: {audio_duration_seconds/60:.0f} min)."
                    )
                else:
                    max_chunk_seconds = 600  # 10-minute chunks for other methods
                    logger.info(f"Audio fits in VRAM but using 10-min chunks for stability (audio: {audio_duration_seconds/60:.0f} min).")
        else:
            # Calculate optimal chunk size that fits in VRAM
            available_for_audio = effective_memory_gb - base_memory_gb
            max_chunk_minutes = available_for_audio / memory_per_minute_gb

            # Cap chunks at reasonable sizes for stability
            if self.enhancement_method == "resemble_enhance":
                # Smaller chunks for Resemble Enhance
                if effective_memory_gb >= 6:  # High-end GPU
                    max_chunk_seconds = min(max_chunk_minutes * 60, 180)  # Max 3 minutes
                else:  # Lower-end GPU
                    max_chunk_seconds = min(max_chunk_minutes * 60, 120)  # Max 2 minutes
            else:
                # Larger chunks for other methods
                if effective_memory_gb >= 6:  # High-end GPU
                    max_chunk_seconds = min(max_chunk_minutes * 60, 600)  # Max 10 minutes
                else:  # Lower-end GPU
                    max_chunk_seconds = min(max_chunk_minutes * 60, 300)  # Max 5 minutes

            logger.info(f"Using VRAM-optimized chunks: {max_chunk_seconds/60:.1f} minutes per chunk.")

        # Ensure minimum chunk size for quality
        max_chunk_seconds = max(10, max_chunk_seconds)  # At least 10 seconds

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

        # Calculate number of chunks
        num_chunks = (len(audio_data) + chunk_size - 1) // chunk_size

        # Process each chunk
        output_audio = np.zeros_like(audio_data)

        for i in range(num_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(audio_data))
            chunk = audio_data[start:end]

            individual_chunk_start = time.time()
            logger.info(f"Processing chunk {i+1}/{num_chunks} with {self.enhancement_method}")

            try:
                if self.enhancement_method == "deepfilternet":
                    processed_chunk = self._process_chunk_deepfilternet(chunk)
                elif self.enhancement_method == "resemble_enhance":
                    processed_chunk = self._process_chunk_resemble_enhance(chunk, sample_rate)
                else:
                    # No enhancement, just copy
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
                orig_len = end - start
                proc_len = len(processed_chunk)
                if proc_len < orig_len:
                    logger.warning(f"Processed chunk shorter than input: input {orig_len}, output {proc_len}. Padding with zeros.")
                    padded = np.zeros(orig_len, dtype=processed_chunk.dtype)
                    padded[:proc_len] = processed_chunk
                    processed_chunk = padded
                elif proc_len > orig_len:
                    logger.warning(f"Processed chunk longer than input: input {orig_len}, output {proc_len}. Trimming.")
                    processed_chunk = processed_chunk[:orig_len]

                processed_chunk = np.clip(processed_chunk, -1.0, 1.0)
                output_audio[start:end] = processed_chunk

            except Exception as e:
                logger.error(f"Error processing chunk {i+1}: {e}")
                # Fall back to original chunk
                output_audio[start:end] = chunk if chunk.ndim == 1 else chunk[0]

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
        """Process a single chunk with DeepFilterNet."""
        if chunk.dtype != np.float32:
            chunk = chunk.astype(np.float32)
        if chunk.ndim == 1:
            chunk = chunk[np.newaxis, :]
        chunk_tensor = torch.from_numpy(chunk).contiguous()
        processed_tensor = enhance(self.df_model, self.df_state, chunk_tensor)
        if isinstance(processed_tensor, torch.Tensor):
            processed_chunk = processed_tensor.cpu().numpy()
        else:
            processed_chunk = processed_tensor
        if processed_chunk.ndim == 2 and processed_chunk.shape[0] == 1:
            processed_chunk = processed_chunk[0]
        return processed_chunk

    def _process_chunk_resemble_enhance(self, chunk: np.ndarray, sample_rate: int) -> np.ndarray:
        """Process a single chunk with Resemble Enhance with GPU/CPU fallback."""

        # Ensure chunk is in the right format
        if chunk.ndim == 2:
            chunk = chunk[0]  # Take first channel if stereo
        chunk = chunk.astype(np.float32)

        try:
            # Process with Resemble Enhance
            if resemble_enhance_available:
                if resemble_enhance_mode == "python_api":
                    # Try GPU first, then CPU fallback
                    return self._try_resemble_enhance_with_fallback(chunk, sample_rate)
                elif resemble_enhance_mode == "command_line":
                    # Use command line tool - requires file-based processing
                    return self._process_chunk_resemble_enhance_file_based(chunk, sample_rate)
            else:
                # Fallback: return original chunk
                return chunk

        except Exception as e:
            logger.warning(f"Resemble Enhance chunk processing failed: {e}, returning original chunk")
            return chunk

    def _try_resemble_enhance_with_fallback(self, chunk: np.ndarray, sample_rate: int) -> np.ndarray:
        """Try GPU processing first, fall back to CPU if needed."""
        import torch

        # Try GPU first
        if torch.cuda.is_available():
            try:
                return self._process_chunk_resemble_enhance_device(chunk, sample_rate, "cuda")
            except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
                logger.warning(f"GPU processing failed ({e}), trying CPU fallback")
                # Clear GPU memory
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        # Fallback to CPU
        try:
            return self._process_chunk_resemble_enhance_device(chunk, sample_rate, "cpu")
        except Exception as e:
            logger.warning(f"CPU fallback also failed ({e}), returning original chunk")
            return chunk

    def _process_chunk_resemble_enhance_device(self, chunk: np.ndarray, sample_rate: int, device_name: str) -> np.ndarray:
        """Process chunk on specific device with proper error handling."""
        import torch

        device = torch.device(device_name)

        # Clear cache if using GPU
        if device_name == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()

        # For GPU processing, try to ensure the model is properly loaded on GPU
        if device_name == "cuda":
            try:
                # Force resemble enhance model to GPU if not already there
                # This is a workaround for the device conflict issue
                import gc
                gc.collect()
                torch.cuda.empty_cache()
            except Exception:
                pass

        # Ensure the audio tensor is properly formatted and on the right device
        if not isinstance(chunk, torch.Tensor):
            audio_tensor = torch.from_numpy(chunk).float()
        else:
            audio_tensor = chunk.float()

        # Make sure tensor is on the correct device
        audio_tensor = audio_tensor.to(device)

        logger.debug(f"Calling denoise with audio tensor shape: {audio_tensor.shape}, sr: {sample_rate}, device: {device}")

        try:
            # Call denoise with correct parameters (audio tensor, sample rate, device)
            enhanced_tensor = denoise(audio_tensor, sample_rate, device)

            # Handle different return types from denoise function
            if isinstance(enhanced_tensor, torch.Tensor):
                enhanced_chunk = enhanced_tensor.detach().cpu().numpy()
            elif isinstance(enhanced_tensor, tuple):
                # Some models return (output, sr) tuple, take the first element
                enhanced_chunk = enhanced_tensor[0]
                if isinstance(enhanced_chunk, torch.Tensor):
                    enhanced_chunk = enhanced_chunk.detach().cpu().numpy()
                elif isinstance(enhanced_chunk, np.ndarray):
                    pass  # Already numpy
                else:
                    enhanced_chunk = np.array(enhanced_chunk)
            elif isinstance(enhanced_tensor, np.ndarray):
                enhanced_chunk = enhanced_tensor
            else:
                # Fallback: convert to numpy if possible
                enhanced_chunk = np.array(enhanced_tensor)

            # Clear tensors from memory
            del audio_tensor
            if isinstance(enhanced_tensor, torch.Tensor):
                del enhanced_tensor
            if device_name == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()

            return enhanced_chunk.astype(np.float32)

        except Exception as e:
            # Clean up tensors even on error
            try:
                if 'audio_tensor' in locals():
                    del locals()['audio_tensor']
                if 'enhanced_tensor' in locals():
                    if isinstance(enhanced_tensor, torch.Tensor):
                        del enhanced_tensor
                    elif isinstance(enhanced_tensor, tuple):
                        for item in enhanced_tensor:
                            if isinstance(item, torch.Tensor):
                                del item
                if device_name == "cuda" and torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            raise e

    def _process_chunk_resemble_enhance_file_based(self, chunk: np.ndarray, sample_rate: int) -> np.ndarray:
        """Process chunk using file-based approach (for command line tool)."""

        # Create temporary files with delete=False to avoid Windows issues
        temp_input = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_output = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)

        try:
            # Save chunk to temporary file with proper format
            # Ensure proper mono format for Resemble Enhance
            sf.write(temp_input.name, chunk, int(sample_rate), format='WAV', subtype='PCM_16')
            temp_input.flush()  # Force write to disk
            temp_input.close()

            # Verify the file was written correctly
            if not os.path.exists(temp_input.name) or os.path.getsize(temp_input.name) == 0:
                logger.warning("Failed to write temporary input file")
                return chunk

            # Process with command line tool
            import subprocess
            result = subprocess.run([
                "resemble-enhance",
                temp_input.name,
                temp_output.name,
                "--denoise_only"
            ], capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                logger.warning(f"Resemble Enhance command failed: {result.stderr}")
                # Fallback: just copy
                import shutil
                shutil.copy2(temp_input.name, temp_output.name)

            # Load processed audio
            processed_chunk, _ = sf.read(temp_output.name)
            # Ensure mono output for consistency
            if processed_chunk.ndim == 2:
                processed_chunk = processed_chunk[:, 0]
            return processed_chunk.astype(np.float32)

        except Exception as e:
            logger.warning(f"File-based Resemble Enhance processing failed: {e}, returning original chunk")
            return chunk

        finally:
            # Clean up temp files - Windows-safe approach
            for temp_file in [temp_input.name, temp_output.name]:
                if os.path.exists(temp_file):
                    try:
                        # Try multiple times with small delays (Windows file lock issue)
                        for attempt in range(3):
                            try:
                                os.unlink(temp_file)
                                break
                            except PermissionError:
                                if attempt < 2:
                                    time.sleep(0.1)  # Small delay
                                else:
                                    logger.warning(f"Could not delete {temp_file} after 3 attempts")
                    except Exception as cleanup_e:
                        logger.warning(f"Failed to clean up {temp_file}: {cleanup_e}")

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

        logger.info(f"Processing audio with {self.enhancement_method} (length: {len(audio_data)} samples)")

        # Route based on enhancement method
        if self.enhancement_method == "resemble_enhance":
            return self._apply_resemble_enhance(audio_data, sample_rate, size_threshold)
        elif self.enhancement_method == "deepfilternet":
            return self._apply_deepfilternet(audio_data, sample_rate, size_threshold)
        elif self.enhancement_method == "none":
            logger.info("No enhancement requested, returning original audio")
            return audio_data
        else:
            logger.warning(f"Unknown enhancement method: {self.enhancement_method}, falling back to no enhancement")
            return audio_data

    def _apply_resemble_enhance(self, audio_data: np.ndarray, sample_rate: int, size_threshold: int = None) -> np.ndarray:
        """Apply Resemble Enhance noise reduction"""
        try:
            # Use dynamic chunk size based on available memory
            optimal_chunk_samples = self.get_optimal_chunk_size(len(audio_data), sample_rate)
            optimal_chunk_seconds = optimal_chunk_samples / sample_rate

            if size_threshold is None or size_threshold > optimal_chunk_samples:
                size_threshold = optimal_chunk_samples
                logger.info(f"Set Resemble Enhance chunking threshold to {size_threshold} samples (dynamic {optimal_chunk_seconds:.1f}s chunks)")

            # Process in chunks if file is large
            if len(audio_data) > size_threshold:
                logger.info("Large audio file detected, processing in chunks")
                return self.process_large_audio_in_chunks(audio_data, sample_rate, chunk_size_seconds=optimal_chunk_seconds)

            # Process normally for smaller files
            logger.info("Using Resemble Enhance for noise reduction")

            # Use the same approach as _process_chunk_resemble_enhance
            import os
            import tempfile

            # Resemble Enhance works with files, so we need to save/load temporarily
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_input:
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
                    try:
                        # Save audio to temporary file
                        sf.write(temp_input.name, audio_data, sample_rate)
                        temp_input.close()

                        # Process with Resemble Enhance
                        if resemble_enhance_available:
                            if resemble_enhance_mode == "python_api":
                                # Use Python API (preferred)
                                try:
                                    # Import torch to get device
                                    import torch
                                    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                                    denoise(temp_input.name, temp_output.name, device=device)
                                except Exception as e:
                                    logger.warning(f"Resemble Enhance Python API failed: {e}, trying command line fallback")
                                    # Try command line as fallback
                                    try:
                                        import subprocess
                                        subprocess.run([
                                            "resemble-enhance",
                                            temp_input.name,
                                            temp_output.name,
                                            "--device", "cuda" if torch.cuda.is_available() else "cpu"
                                        ], check=True, capture_output=True, text=True)
                                        logger.info("Resemble Enhance command line succeeded")
                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"Resemble Enhance command line failed: {e}")
                                        raise e
                            else:
                                # Use command line only
                                import subprocess
                                subprocess.run([
                                    "resemble-enhance",
                                    temp_input.name,
                                    temp_output.name,
                                    "--device", "cuda" if torch.cuda.is_available() else "cpu"
                                ], check=True, capture_output=True, text=True)
                                logger.info("Resemble Enhance command line succeeded")
                        else:
                            raise RuntimeError("Resemble Enhance not available")

                        # Load processed audio
                        temp_output.close()
                        processed_audio, _ = sf.read(temp_output.name)

                        # Ensure output length matches input
                        if len(processed_audio) != len(audio_data):
                            logger.warning(f"Resemble Enhance output length {len(processed_audio)} does not match input {len(audio_data)}. Padding or trimming as needed.")
                            if len(processed_audio) < len(audio_data):
                                padded = np.zeros(len(audio_data), dtype=processed_audio.dtype)
                                padded[:len(processed_audio)] = processed_audio
                                processed_audio = padded
                            else:
                                processed_audio = processed_audio[:len(audio_data)]

                        logger.info("Resemble Enhance noise reduction completed successfully")
                        return processed_audio.astype(np.float32)

                    finally:
                        # Clean up temporary files
                        try:
                            if os.path.exists(temp_input.name):
                                os.unlink(temp_input.name)
                            if os.path.exists(temp_output.name):
                                os.unlink(temp_output.name)
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"Resemble Enhance processing failed: {e}")
            logger.warning("Falling back to custom noise reduction")
            return self.custom_noise_reduction(audio_data, sample_rate, noise_reduction_amount=0.7)

    def _apply_deepfilternet(self, audio_data: np.ndarray, sample_rate: int, size_threshold: int = None) -> np.ndarray:
        """Apply DeepFilterNet noise reduction"""
        start_time = time.time()

        logger.info(f"Processing audio with DeepFilterNet (length: {len(audio_data)} samples)")

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
                return result
            # Process normally for smaller files
            logger.info("Using DeepFilterNet for noise reduction")
            single_start_time = time.time()

            if audio_data.ndim == 1:
                audio_data = audio_data[np.newaxis, :]
            audio_tensor = torch.from_numpy(audio_data).contiguous()
            processed_tensor = enhance(self.df_model, self.df_state, audio_tensor)

            if isinstance(processed_tensor, torch.Tensor):
                reduced_noise = processed_tensor.cpu().numpy()
            else:
                reduced_noise = processed_tensor
            if reduced_noise.ndim == 2 and reduced_noise.shape[0] == 1:
                reduced_noise = reduced_noise[0]

            single_end_time = time.time()
            total_time = single_end_time - start_time
            processing_time = single_end_time - single_start_time
            logger.info(f"⏱️  SINGLE PROCESSING: Total time {total_time:.1f}s, Pure processing: {processing_time:.1f}s")
            # Ensure output length matches input
            if reduced_noise.shape[0] != audio_data.shape[-1]:
                logger.warning(f"DeepFilterNet output length {reduced_noise.shape[0]} does not match input {audio_data.shape[-1]}. Padding or trimming as needed.")
                if reduced_noise.shape[0] < audio_data.shape[-1]:
                    padded = np.zeros(audio_data.shape[-1], dtype=reduced_noise.dtype)
                    padded[:reduced_noise.shape[0]] = reduced_noise
                    reduced_noise = padded
                else:
                    reduced_noise = reduced_noise[:audio_data.shape[-1]]
            logger.info("DeepFilterNet noise reduction completed successfully")
            return reduced_noise
        except Exception as e:
            logger.error(f"DeepFilterNet processing failed: {e}")
            logger.warning("Falling back to custom noise reduction")
            return self.custom_noise_reduction(audio_data, sample_rate, noise_reduction_amount=0.7)

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
        gain_linear = 10 ** (gain_db / 15.0)

        # Apply gain
        amplified = audio_data * gain_linear

        # Prevent clipping
        amplified = np.clip(amplified, -1.0, 1.0)

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
                    max_duration_minutes: int | None = None) -> bool:
        """
        Complete sermon audio processing pipeline with safeguards for large files.
                        max_duration_minutes: Optional[int] = None) -> bool:
        Args:
            input_path: Input audio file path
            output_path: Output audio file path
            noise_reduction: Apply noise reduction
            amplify: Apply amplification
            normalize: Apply normalization
            gain_db: Amplification gain in dB
            target_level_db: Target normalization level in dB
            max_duration_minutes: Maximum duration to process in minutes (for safety)

        Returns:
                        max_duration_minutes: Maximum duration to process in minutes (None for no limit)
        """
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
            # Apply noise reduction if requested
            if noise_reduction:
                audio_data = self.apply_noise_reduction(audio_data, sample_rate)
            # Clip after noise reduction
            audio_data = np.clip(audio_data, -1.0, 1.0)
            # Apply amplification or normalization, not both
            if normalize:
                audio_data = self.normalize_audio(audio_data, target_level_db)
            elif amplify:
                audio_data = self.amplify_audio(audio_data, gain_db)
            # Clip after gain/normalization
            audio_data = np.clip(audio_data, -1.0, 1.0)
            # Final peak normalization and hard limiter before saving
            audio_data = peak_normalize(audio_data, peak_db=-1.0)
            audio_data = np.clip(audio_data, -0.98, 0.98)
            self.save_audio(audio_data, sample_rate, output_path)
            logger.info("Audio processing completed successfully")
            return True
        except Exception as e:
            logger.error(f"Audio processing failed: {e}")
            return False



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
                       skip_on_error: bool = True, enhancement_method: str = "resemble_enhance",
                       verbose: bool = False, **kwargs) -> bool:
    """
    Process sermon audio with selected enhancement method.

    Args:
        input_path: Input audio file
        output_path: Output audio file
        use_audacity: Use Audacity if True, else use native Python processing
        enhancement_method: AI enhancement method to use ("resemble_enhance", "deepfilternet", "none")
        verbose: Show detailed processing information
        **kwargs: Additional arguments for processing

    Returns:
        Success status
    """
    if use_audacity:
        processor = AudacityProcessor()
        if processor.pipe_exists:
            return processor.process_with_macro(input_path, output_path)
        else:
            logger.warning(f"Audacity not available, using {enhancement_method} processing")

    # Use AI enhancement processing
    try:
        # Suppress DF logs if not in verbose mode
        if not verbose and enhancement_method.lower() == "deepfilternet":
            # Completely suppress DF output
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                processor = AudioProcessor(enhancement_method=enhancement_method)
                result = processor.process_sermon_audio(input_path, output_path, **kwargs)
            return result
        else:
            processor = AudioProcessor(enhancement_method=enhancement_method)
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
                return True
            except Exception as copy_error:
                logger.error(f"Failed to copy original file: {copy_error}")
                return False
        else:
            # Re-raise the exception if skip_on_error is False
            raise
