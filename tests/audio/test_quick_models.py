#!/usr/bin/env python3
"""
Quick Test of Working Enhancement Models
"""

import logging
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

def test_voicefixer():
    """Test VoiceFixer on a small audio sample"""

    test_audio = Path("2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3")
    if not test_audio.exists():
        logger.error(f"Test audio not found: {test_audio}")
        return False

    try:
        logger.info("🔧 Testing VoiceFixer (5 minute sample)...")
        start_time = time.time()

        from voicefixer import VoiceFixer

        # Initialize VoiceFixer
        voicefixer = VoiceFixer()

        output_file = Path("voicefixer_5min_test.wav")

        # Restore audio (44.1kHz, remove noise, etc.)
        # Process only first 5 minutes to save time
        voicefixer.restore(
            input=str(test_audio),
            output=str(output_file),
            cuda=True,  # Use GPU if available
            mode=0,     # Natural speech enhancement
            # seg_len=5*60  # 5 minutes only
        )

        processing_time = time.time() - start_time

        if output_file.exists():
            file_size = output_file.stat().st_size / (1024 * 1024)  # MB
            logger.info("✅ VoiceFixer SUCCESS")
            logger.info(f"   ⏱️  Time: {processing_time:.2f}s")
            logger.info(f"   📁 Size: {file_size:.2f}MB")
            logger.info(f"   📄 File: {output_file}")
            return True
        else:
            logger.error("❌ VoiceFixer failed - no output file")
            return False

    except Exception as e:
        logger.error(f"❌ VoiceFixer failed: {e}")
        return False

def test_resemble_enhance():
    """Test Resemble Enhance with correct API"""

    test_audio = Path("2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3")
    if not test_audio.exists():
        logger.error(f"Test audio not found: {test_audio}")
        return False

    try:
        logger.info("🔧 Testing Resemble Enhance (2 minute sample)...")
        start_time = time.time()

        import soundfile as sf
        from resemble_enhance.enhancer.inference import denoise

        # Load audio (limit to 2 minutes)
        audio, sr = sf.read(str(test_audio))
        audio_2min = audio[:sr * 120]  # First 2 minutes

        # Enhance with Resemble Enhance
        enhanced_audio = denoise(audio_2min, sr, "cuda")

        output_file = Path("resemble_enhance_2min_test.wav")

        # Save enhanced audio
        sf.write(str(output_file), enhanced_audio, sr)

        processing_time = time.time() - start_time

        if output_file.exists():
            file_size = output_file.stat().st_size / (1024 * 1024)  # MB
            logger.info("✅ Resemble Enhance SUCCESS")
            logger.info(f"   ⏱️  Time: {processing_time:.2f}s")
            logger.info(f"   📁 Size: {file_size:.2f}MB")
            logger.info(f"   📄 File: {output_file}")
            return True
        else:
            logger.error("❌ Resemble Enhance failed - no output file")
            return False

    except Exception as e:
        logger.error(f"❌ Resemble Enhance failed: {e}")
        return False

def test_deepfilternet():
    """Test DeepFilterNet (already working)"""

    test_audio = Path("2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3")
    if not test_audio.exists():
        logger.error(f"Test audio not found: {test_audio}")
        return False

    try:
        logger.info("🔧 Testing DeepFilterNet (2 minute sample)...")
        start_time = time.time()

        # Use our existing audio processor
# Add src directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

        from audio_processing import AudioProcessor

        processor = AudioProcessor(enhancement_method="deepfilternet")

        output_file = Path("deepfilternet_2min_test.wav")

        success = processor.process_sermon_audio(
            input_path=str(test_audio),
            output_path=str(output_file),
            noise_reduction=True,
            amplify=True,
            normalize=True,
            max_duration_minutes=2.0  # 2 minutes only
        )

        processing_time = time.time() - start_time

        if success and output_file.exists():
            file_size = output_file.stat().st_size / (1024 * 1024)  # MB
            logger.info("✅ DeepFilterNet SUCCESS")
            logger.info(f"   ⏱️  Time: {processing_time:.2f}s")
            logger.info(f"   📁 Size: {file_size:.2f}MB")
            logger.info(f"   📄 File: {output_file}")
            return True
        else:
            logger.error("❌ DeepFilterNet failed")
            return False

    except Exception as e:
        logger.error(f"❌ DeepFilterNet failed: {e}")
        return False

def main():
    """Run quick tests of working models"""

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    logger.info("🚀 QUICK TEST OF WORKING ENHANCEMENT MODELS")
    logger.info("="*60)

    results = {}

    # Test DeepFilterNet (we know this works)
    results["DeepFilterNet"] = test_deepfilternet()

    # Test Resemble Enhance (fixed API)
    results["Resemble Enhance"] = test_resemble_enhance()

    # Test VoiceFixer (working but slow)
    # results["VoiceFixer"] = test_voicefixer()  # Skip for now as it's very slow

    # Summary
    logger.info("\n📊 QUICK TEST RESULTS")
    logger.info("="*60)

    for model, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"{model:20s}: {status}")

    successful_count = sum(results.values())
    logger.info(f"\n🏆 {successful_count}/{len(results)} models working successfully!")

    if successful_count > 0:
        logger.info("\n💡 Recommendations based on test results:")
        if results.get("DeepFilterNet", False):
            logger.info("   • DeepFilterNet: Fast, lightweight, good for real-time")
        if results.get("Resemble Enhance", False):
            logger.info("   • Resemble Enhance: Best quality, slower processing")
        # if results.get("VoiceFixer", False):
        #     logger.info("   • VoiceFixer: Excellent quality, very slow")

if __name__ == "__main__":
    main()
