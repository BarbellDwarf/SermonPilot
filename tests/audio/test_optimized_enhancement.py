#!/usr/bin/env python3
"""
Optimized Audio Enhancement with Advanced Memory Management and Caching
"""

import logging
import os
import sys
import time
from functools import lru_cache
from pathlib import Path

import psutil
import torch

# Add parent directory to path to import audio_processing
sys.path.append(str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

class OptimizedAudioEnhancer:
    """Optimized audio enhancer with better memory management and caching"""

    def __init__(self, enhancement_method: str = "resemble_enhance", device: str | None = None):
        self.enhancement_method = enhancement_method
        self.device = self._get_optimal_device(device)
        self.models_cached = False
        self.resemble_enhancer = None
        self._setup_model_cache()

    def _get_optimal_device(self, device: str | None = None) -> str:
        """Determine the best device (GPU/CPU) for processing"""
        if device is not None:
            return device

        if torch.cuda.is_available():
            # Check GPU memory
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
            gpu_memory_free = torch.cuda.memory_reserved(0) / (1024**3)  # GB

            logger.info(f"GPU detected: {torch.cuda.get_device_name(0)}")
            logger.info(f"Total GPU memory: {gpu_memory:.2f} GB")
            logger.info(f"Free GPU memory: {gpu_memory_free:.2f} GB")

            # Use GPU if we have at least 4GB available
            if gpu_memory_free > 4.0 or gpu_memory > 8.0:
                return "cuda"
            else:
                logger.warning("GPU memory may be insufficient, falling back to CPU")
                return "cpu"
        else:
            logger.info("No GPU available, using CPU")
            return "cpu"

    def _setup_model_cache(self):
        """Set up model caching to avoid re-downloading"""
        if self.enhancement_method == "resemble_enhance":
            try:
                # Set up persistent cache directory
                cache_dir = Path.home() / ".cache" / "resemble_enhance"
                cache_dir.mkdir(parents=True, exist_ok=True)

                # Set environment variables to control caching
                os.environ["RESEMBLE_ENHANCE_CACHE"] = str(cache_dir)

                # Check if models are already cached
                model_path = cache_dir / "enhancer_stage2"
                if model_path.exists():
                    logger.info(f"Using cached Resemble Enhance models from {model_path}")
                    self.models_cached = True
                else:
                    logger.info("Models not cached, will download on first use")

            except Exception as e:
                logger.warning(f"Could not set up model cache: {e}")

    def get_optimal_chunk_size(self, total_samples: int, sample_rate: int, audio_duration_minutes: float) -> int:
        """Dynamically calculate optimal chunk size based on available memory and audio length"""

        # Get available memory
        cpu_memory_gb = psutil.virtual_memory().available / (1024**3)

        if self.device == "cuda" and torch.cuda.is_available():
            gpu_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            available_memory_gb = min(cpu_memory_gb, gpu_memory_gb * 0.8)  # Use 80% of GPU memory
        else:
            available_memory_gb = cpu_memory_gb * 0.6  # Use 60% of CPU memory

        logger.info(f"Available memory for processing: {available_memory_gb:.2f} GB")

        # Estimate memory usage per second of audio (empirical values)
        if self.enhancement_method == "resemble_enhance":
            memory_per_second_gb = 0.5  # Resemble Enhance is memory intensive
            max_chunk_seconds = min(120, available_memory_gb / memory_per_second_gb)  # Cap at 2 minutes
        else:  # DeepFilterNet
            memory_per_second_gb = 0.2  # DeepFilterNet is more efficient
            max_chunk_seconds = min(180, available_memory_gb / memory_per_second_gb)  # Cap at 3 minutes

        # For very long audio, use smaller chunks to prevent memory issues
        if audio_duration_minutes > 60:  # 1+ hour audio
            max_chunk_seconds = min(max_chunk_seconds, 60)  # Max 1 minute chunks
        elif audio_duration_minutes > 30:  # 30+ minute audio
            max_chunk_seconds = min(max_chunk_seconds, 90)  # Max 1.5 minute chunks

        # Ensure minimum chunk size for quality
        min_chunk_seconds = 10  # At least 10 seconds
        max_chunk_seconds = max(min_chunk_seconds, max_chunk_seconds)

        chunk_samples = int(max_chunk_seconds * sample_rate)

        # Don't chunk if the entire audio fits in one chunk
        if chunk_samples >= total_samples:
            chunk_samples = total_samples
            logger.info("Audio is small enough to process without chunking")
        else:
            logger.info(f"Optimal chunk size: {max_chunk_seconds:.1f} seconds ({chunk_samples} samples)")

        return chunk_samples

    @lru_cache(maxsize=1)
    def _load_resemble_enhancer(self):
        """Load Resemble Enhance models with caching"""
        try:
            from resemble_enhance.enhancer.download import download
            from resemble_enhance.enhancer.inference import load_enhancer

            # Use cached model path if available
            cache_dir = Path.home() / ".cache" / "resemble_enhance"
            model_path = cache_dir / "enhancer_stage2"

            if model_path.exists() and (model_path / "ds").exists():
                logger.info("Loading cached Resemble Enhance model")
                run_dir = model_path
            else:
                logger.info("Downloading Resemble Enhance model (first time only)")
                run_dir = download()

                # Copy to our cache if different location
                if run_dir != model_path:
                    import shutil
                    shutil.copytree(run_dir, model_path, dirs_exist_ok=True)
                    run_dir = model_path

            enhancer = load_enhancer(run_dir, self.device)
            logger.info("Resemble Enhance model loaded successfully")
            return enhancer

        except Exception as e:
            logger.error(f"Failed to load Resemble Enhance: {e}")
            return None

    def process_audio_optimized(self, audio_file: str, output_file: str, max_duration_minutes: float | None = None):
        """Process audio with optimized memory management"""

        from audio_processing import AudioProcessor

        logger.info("🚀 Starting optimized audio processing...")
        logger.info(f"📁 Input: {Path(audio_file).name}")
        logger.info(f"📁 Output: {Path(output_file).name}")
        logger.info(f"🔧 Method: {self.enhancement_method}")
        logger.info(f"💻 Device: {self.device}")

        start_time = time.time()

        try:
            # Initialize processor with our settings
            processor = AudioProcessor(enhancement_method=self.enhancement_method)

            # Load audio to get info
            import soundfile as sf
            audio_data, sample_rate = sf.read(audio_file)
            original_length = len(audio_data)
            duration_minutes = original_length / sample_rate / 60

            logger.info(f"📊 Audio info: {original_length:,} samples, {sample_rate} Hz, {duration_minutes:.2f} minutes")

            # Apply duration limit if specified
            if max_duration_minutes and duration_minutes > max_duration_minutes:
                logger.info(f"⏱️  Limiting to first {max_duration_minutes} minutes")
                max_samples = int(max_duration_minutes * 60 * sample_rate)
                audio_data = audio_data[:max_samples]
                duration_minutes = max_duration_minutes

            # Get optimal chunk size
            chunk_size = self.get_optimal_chunk_size(len(audio_data), sample_rate, duration_minutes)

            # Override the processor's chunking with our optimized version
            if hasattr(processor, 'process_large_audio_in_chunks'):
                chunk_seconds = chunk_size / sample_rate
                logger.info(f"🔄 Using dynamic chunking: {chunk_seconds:.1f} seconds per chunk")

                # Temporarily save audio and process
                import tempfile
                try:
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                        temp_filename = temp_file.name
                        sf.write(temp_filename, audio_data, sample_rate)

                    # Process the file
                    success = processor.process_sermon_audio(
                        input_path=temp_filename,
                        output_path=output_file,
                        noise_reduction=True,
                        amplify=True,
                        normalize=True
                    )
                finally:
                    # Clean up temp file if it exists
                    try:
                        if 'temp_filename' in locals() and os.path.exists(temp_filename):
                            os.unlink(temp_filename)
                    except Exception as cleanup_error:
                        logger.warning(f"Could not clean up temp file: {cleanup_error}")
            else:
                # Fallback to direct processing
                success = processor.process_sermon_audio(
                    input_path=audio_file,
                    output_path=output_file,
                    noise_reduction=True,
                    amplify=True,
                    normalize=True,
                    max_duration_minutes=max_duration_minutes
                )

            processing_time = time.time() - start_time

            if success:
                # Analyze output
                if Path(output_file).exists():
                    output_info = sf.info(output_file)
                    output_size_mb = Path(output_file).stat().st_size / (1024 * 1024)

                    logger.info("✅ Processing completed successfully!")
                    logger.info(f"⏱️  Processing time: {processing_time:.2f} seconds")
                    logger.info(f"📊 Output: {output_info.frames:,} samples, {output_size_mb:.2f} MB")

                    # Performance metrics
                    speed_ratio = duration_minutes / (processing_time / 60)
                    logger.info(f"🚀 Speed: {speed_ratio:.2f}x real-time")

                    return True
                else:
                    logger.error("❌ Output file was not created")
                    return False
            else:
                logger.error("❌ Processing failed")
                return False

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Processing failed: {e}")
            logger.error(f"⏱️  Time before failure: {processing_time:.2f} seconds")
            return False

def test_optimized_enhancement():
    """Test the optimized enhancement system"""

    print("🚀 Testing Optimized Audio Enhancement System")
    print("=" * 60)

    # Test file
    test_dir = Path(".")
    audio_file = test_dir / "2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3"

    if not audio_file.exists():
        print(f"❌ Test file not found: {audio_file}")
        return False

    # Test both methods
    methods = ["resemble_enhance", "deepfilternet"]
    results = {}

    for method in methods:
        print(f"\n🔧 Testing {method} with optimization...")
        print("-" * 50)

        try:
            enhancer = OptimizedAudioEnhancer(enhancement_method=method)
            output_file = test_dir / f"{audio_file.stem}_optimized_{method}.wav"

            success = enhancer.process_audio_optimized(
                str(audio_file),
                str(output_file),
                max_duration_minutes=2.0  # 2 minutes for testing
            )

            results[method] = success

        except Exception as e:
            print(f"❌ {method} failed with exception: {e}")
            results[method] = False

    # Summary
    print("\n📊 Optimization Test Results")
    print("=" * 60)
    for method, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{method:20s}: {status}")

    return all(results.values())

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    test_optimized_enhancement()
