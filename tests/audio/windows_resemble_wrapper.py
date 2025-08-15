
import logging
import subprocess
import tempfile

import torch

logger = logging.getLogger(__name__)

class WindowsCompatibleResembleEnhancer:
    """Windows-compatible wrapper for Resemble Enhance"""

    def __init__(self, device="cuda"):
        self.device = device
        self.available = self._check_availability()

    def _check_availability(self):
        """Check if resemble-enhance command line is available"""
        try:
            import shutil
            return shutil.which("resemble-enhance") is not None
        except:
            return False

    def enhance_audio(self, input_path, output_path, denoise_only=False):
        """Enhance audio using command line interface (avoids Python API issues)"""
        if not self.available:
            raise RuntimeError("resemble-enhance command not available")

        cmd = ["resemble-enhance", input_path, output_path]
        if denoise_only:
            cmd.append("--denoise_only")

        # Add device selection if CUDA available
        if self.device == "cuda" and torch.cuda.is_available():
            cmd.extend(["--device", "cuda"])
        else:
            cmd.extend(["--device", "cpu"])

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info("Resemble Enhance completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Resemble Enhance failed: {e.stderr}")
            raise e

    def process_chunk(self, audio_chunk, sample_rate):
        """Process a single audio chunk"""
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_input:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
                try:
                    # Save chunk
                    sf.write(temp_input.name, audio_chunk, sample_rate)
                    temp_input.close()

                    # Process
                    self.enhance_audio(temp_input.name, temp_output.name)

                    # Load result
                    temp_output.close()
                    enhanced_chunk, _ = sf.read(temp_output.name)

                    return enhanced_chunk

                finally:
                    # Cleanup
                    import os
                    try:
                        if os.path.exists(temp_input.name):
                            os.unlink(temp_input.name)
                        if os.path.exists(temp_output.name):
                            os.unlink(temp_output.name)
                    except:
                        pass
