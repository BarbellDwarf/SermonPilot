#!/usr/bin/env python3
"""
Testing Best-in-Class Speech Enhancement Models (2024)

Based on research, testing these promising models:
1. Resemble Enhance - Current best for speech super resolution
2. DeepFilterNet - Fast, lightweight noise suppression  
3. VoiceFixer - Unified speech restoration framework
4. SpeechBrain enhancement models - State-of-the-art toolkit
5. Facebook Demucs - Real-time waveform domain enhancement
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

import torch

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

class BestModelsTester:
    """Test and compare best speech enhancement models of 2024"""

    def __init__(self):
        self.test_audio = Path("2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3")
        self.results_dir = Path("enhancement_model_results")
        self.results_dir.mkdir(exist_ok=True)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Model availability status
        self.available_models = {}
        self._check_model_availability()

    def _check_model_availability(self):
        """Check which enhancement models are available"""

        models_to_check = {
            "resemble_enhance": self._check_resemble_enhance,
            "deepfilternet": self._check_deepfilternet,
            "voicefixer": self._check_voicefixer,
            "speechbrain": self._check_speechbrain,
            "demucs": self._check_demucs
        }

        for model_name, check_func in models_to_check.items():
            try:
                self.available_models[model_name] = check_func()
                status = "✅ Available" if self.available_models[model_name] else "❌ Not available"
                logger.info(f"{model_name:15s}: {status}")
            except Exception as e:
                self.available_models[model_name] = False
                logger.warning(f"{model_name:15s}: ❌ Check failed - {e}")

    def _check_resemble_enhance(self) -> bool:
        """Check if Resemble Enhance is available"""
        try:
            import resemble_enhance
            from resemble_enhance.enhancer.inference import denoise
            return True
        except ImportError:
            return False

    def _check_deepfilternet(self) -> bool:
        """Check if DeepFilterNet is available"""
        try:
            import deepfilternet
            from deepfilternet.df.enhance import enhance
            return True
        except ImportError:
            return False

    def _check_voicefixer(self) -> bool:
        """Check if VoiceFixer is available"""
        try:
            # Check if pip package exists
            import pkg_resources
            pkg_resources.get_distribution("voicefixer")
            return True
        except:
            # Check if can install
            return False

    def _check_speechbrain(self) -> bool:
        """Check if SpeechBrain is available"""
        try:
            import speechbrain
            return True
        except ImportError:
            return False

    def _check_demucs(self) -> bool:
        """Check if Demucs is available"""
        try:
            import demucs
            return True
        except ImportError:
            return False

    def install_voicefixer(self) -> bool:
        """Install VoiceFixer if not available"""
        try:
            logger.info("📦 Installing VoiceFixer...")
            subprocess.run([
                sys.executable, "-m", "pip", "install",
                "voicefixer", "--quiet"
            ], check=True)

            # Verify installation
            logger.info("✅ VoiceFixer installed successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to install VoiceFixer: {e}")
            return False

    def install_speechbrain(self) -> bool:
        """Install SpeechBrain if not available"""
        try:
            logger.info("📦 Installing SpeechBrain...")
            subprocess.run([
                sys.executable, "-m", "pip", "install",
                "speechbrain", "--quiet"
            ], check=True)

            # Verify installation
            logger.info("✅ SpeechBrain installed successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to install SpeechBrain: {e}")
            return False

    def install_demucs(self) -> bool:
        """Install Demucs if not available"""
        try:
            logger.info("📦 Installing Demucs...")
            subprocess.run([
                sys.executable, "-m", "pip", "install",
                "demucs", "--quiet"
            ], check=True)

            # Verify installation
            logger.info("✅ Demucs installed successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to install Demucs: {e}")
            return False

    def test_resemble_enhance(self) -> dict:
        """Test Resemble Enhance (current best)"""

        if not self.available_models.get("resemble_enhance", False):
            return {"status": "unavailable", "error": "Model not available"}

        try:
            logger.info("🔧 Testing Resemble Enhance...")
            start_time = time.time()

            import soundfile as sf
            from resemble_enhance.enhancer.inference import denoise

            # Load audio
            audio, sr = sf.read(str(self.test_audio))

            # Enhance with Resemble Enhance
            enhanced_audio = denoise(audio, sr, self.device)

            output_file = self.results_dir / f"{self.test_audio.stem}_resemble_enhance.wav"

            # Save enhanced audio
            sf.write(str(output_file), enhanced_audio, sr)

            processing_time = time.time() - start_time

            if output_file.exists():
                file_size = output_file.stat().st_size / (1024 * 1024)  # MB
                return {
                    "status": "success",
                    "processing_time": processing_time,
                    "output_size_mb": file_size,
                    "output_file": str(output_file)
                }
            else:
                return {"status": "failed", "error": "Output file not created"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def test_deepfilternet(self) -> dict:
        """Test DeepFilterNet (fast, lightweight)"""

        if not self.available_models.get("deepfilternet", False):
            return {"status": "unavailable", "error": "Model not available"}

        try:
            logger.info("🔧 Testing DeepFilterNet...")
            start_time = time.time()

            import soundfile as sf
            from deepfilternet.df.enhance import enhance, init_df

            # Initialize DeepFilterNet
            model, df_state, _ = init_df(
                config_allow_defaults=True
            )

            # Load audio
            audio, sr = sf.read(str(self.test_audio))

            # Enhance audio
            enhanced_audio = enhance(model, df_state, audio, sr)

            # Save enhanced audio
            output_file = self.results_dir / f"{self.test_audio.stem}_deepfilternet.wav"
            sf.write(str(output_file), enhanced_audio, sr)

            processing_time = time.time() - start_time

            if output_file.exists():
                file_size = output_file.stat().st_size / (1024 * 1024)  # MB
                return {
                    "status": "success",
                    "processing_time": processing_time,
                    "output_size_mb": file_size,
                    "output_file": str(output_file)
                }
            else:
                return {"status": "failed", "error": "Output file not created"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def test_voicefixer(self) -> dict:
        """Test VoiceFixer (unified speech restoration)"""

        # Try to install if not available
        if not self.available_models.get("voicefixer", False):
            if not self.install_voicefixer():
                return {"status": "unavailable", "error": "Could not install VoiceFixer"}

        try:
            logger.info("🔧 Testing VoiceFixer...")
            start_time = time.time()

            from voicefixer import VoiceFixer

            # Initialize VoiceFixer
            voicefixer = VoiceFixer()

            output_file = self.results_dir / f"{self.test_audio.stem}_voicefixer.wav"

            # Restore audio (44.1kHz, remove noise, etc.)
            voicefixer.restore(
                input=str(self.test_audio),
                output=str(output_file),
                cuda=torch.cuda.is_available(),
                # mode=0 for natural speech enhancement
                mode=0
            )

            processing_time = time.time() - start_time

            if output_file.exists():
                file_size = output_file.stat().st_size / (1024 * 1024)  # MB
                return {
                    "status": "success",
                    "processing_time": processing_time,
                    "output_size_mb": file_size,
                    "output_file": str(output_file)
                }
            else:
                return {"status": "failed", "error": "Output file not created"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def test_speechbrain(self) -> dict:
        """Test SpeechBrain speech enhancement"""

        # Try to install if not available
        if not self.available_models.get("speechbrain", False):
            if not self.install_speechbrain():
                return {"status": "unavailable", "error": "Could not install SpeechBrain"}

        try:
            logger.info("🔧 Testing SpeechBrain...")
            start_time = time.time()

            from speechbrain.pretrained import SepformerSeparation as separator

            # Use pre-trained speech enhancement model
            model = separator.from_hparams(
                source="speechbrain/sepformer-wham-enhancement",
                savedir='pretrained_models/sepformer-wham-enhancement'
            )

            # Enhance audio
            est_sources = model.separate_file(path=str(self.test_audio))

            output_file = self.results_dir / f"{self.test_audio.stem}_speechbrain.wav"

            # Save enhanced audio (first source)
            import torchaudio
            torchaudio.save(str(output_file), est_sources[:, :, 0].cpu(), 8000)

            processing_time = time.time() - start_time

            if output_file.exists():
                file_size = output_file.stat().st_size / (1024 * 1024)  # MB
                return {
                    "status": "success",
                    "processing_time": processing_time,
                    "output_size_mb": file_size,
                    "output_file": str(output_file)
                }
            else:
                return {"status": "failed", "error": "Output file not created"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def test_demucs(self) -> dict:
        """Test Demucs (Facebook's real-time enhancement)"""

        # Try to install if not available
        if not self.available_models.get("demucs", False):
            if not self.install_demucs():
                return {"status": "unavailable", "error": "Could not install Demucs"}

        try:
            logger.info("🔧 Testing Demucs...")
            start_time = time.time()

            # Use Demucs CLI for speech enhancement
            output_file = self.results_dir / f"{self.test_audio.stem}_demucs.wav"

            # Run demucs command for speech enhancement
            cmd = [
                sys.executable, "-m", "demucs.separate",
                "--name", "htdemucs",  # Use htdemucs model
                "--out", str(self.results_dir),
                str(self.test_audio)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            processing_time = time.time() - start_time

            # Find the enhanced output file
            demucs_output_dir = self.results_dir / "htdemucs" / self.test_audio.stem
            if demucs_output_dir.exists():
                # Find the vocals/speech component
                vocals_file = demucs_output_dir / "vocals.wav"
                if vocals_file.exists():
                    # Copy to our standardized output name
                    import shutil
                    shutil.copy2(vocals_file, output_file)

                    file_size = output_file.stat().st_size / (1024 * 1024)  # MB
                    return {
                        "status": "success",
                        "processing_time": processing_time,
                        "output_size_mb": file_size,
                        "output_file": str(output_file)
                    }

            return {"status": "failed", "error": f"Demucs output not found. stderr: {result.stderr}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run_comprehensive_test(self) -> dict:
        """Run comprehensive test of all available models"""

        if not self.test_audio.exists():
            logger.error(f"❌ Test audio file not found: {self.test_audio}")
            return {}

        logger.info(f"🎵 Testing with audio: {self.test_audio.name}")
        logger.info(f"💾 Results directory: {self.results_dir}")
        logger.info(f"💻 Device: {self.device}")

        # Test methods
        test_methods = {
            "resemble_enhance": self.test_resemble_enhance,
            "deepfilternet": self.test_deepfilternet,
            "voicefixer": self.test_voicefixer,
            "speechbrain": self.test_speechbrain,
            "demucs": self.test_demucs
        }

        results = {}

        for model_name, test_method in test_methods.items():
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing {model_name.upper()}")
            logger.info(f"{'='*60}")

            try:
                result = test_method()
                results[model_name] = result

                if result["status"] == "success":
                    logger.info(f"✅ {model_name} - SUCCESS")
                    logger.info(f"   ⏱️  Time: {result['processing_time']:.2f}s")
                    logger.info(f"   📁 Size: {result['output_size_mb']:.2f}MB")
                    logger.info(f"   📄 File: {Path(result['output_file']).name}")
                elif result["status"] == "unavailable":
                    logger.warning(f"⏭️  {model_name} - UNAVAILABLE: {result['error']}")
                else:
                    logger.error(f"❌ {model_name} - FAILED: {result['error']}")

            except Exception as e:
                logger.error(f"❌ {model_name} - EXCEPTION: {e}")
                results[model_name] = {"status": "exception", "error": str(e)}

        return results

    def print_comparison_summary(self, results: dict):
        """Print a comparison summary of all models"""

        logger.info(f"\n{'🏆 ENHANCEMENT MODEL COMPARISON SUMMARY'}")
        logger.info(f"{'='*70}")

        successful_models = [
            name for name, result in results.items()
            if result.get("status") == "success"
        ]

        if not successful_models:
            logger.warning("❌ No models completed successfully")
            return

        # Sort by processing time (fastest first)
        sorted_models = sorted(
            successful_models,
            key=lambda name: results[name]["processing_time"]
        )

        logger.info(f"{'Model':<20} {'Time (s)':<10} {'Size (MB)':<12} {'Status'}")
        logger.info(f"{'-'*60}")

        for i, model_name in enumerate(sorted_models):
            result = results[model_name]
            time_str = f"{result['processing_time']:.2f}"
            size_str = f"{result['output_size_mb']:.2f}"

            rank_emoji = ["🥇", "🥈", "🥉"][min(i, 2)]
            logger.info(f"{model_name:<20} {time_str:<10} {size_str:<12} ✅ {rank_emoji}")

        # Show failed/unavailable models
        failed_models = [
            name for name, result in results.items()
            if result.get("status") != "success"
        ]

        if failed_models:
            logger.info(f"\n{'Unavailable/Failed Models'}")
            logger.info(f"{'-'*40}")
            for model_name in failed_models:
                result = results[model_name]
                status = result.get("status", "unknown")
                error = result.get("error", "No error info")
                logger.info(f"{model_name:<20} ❌ {status}: {error[:40]}...")

def main():
    """Main test runner"""

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    logger.info("🚀 TESTING BEST SPEECH ENHANCEMENT MODELS (2024)")
    logger.info("="*70)

    # Create tester
    tester = BestModelsTester()

    # Run comprehensive test
    results = tester.run_comprehensive_test()

    # Print summary
    tester.print_comparison_summary(results)

    logger.info(f"\n✅ Testing complete! Results saved in: {tester.results_dir}")

    return results

if __name__ == "__main__":
    main()
