#!/usr/bin/env python3
"""
Comprehensive test for Resemble Enhance on real sermon audio
Tests the enhanced audio processing pipeline with the Mark Hogan sermon
"""

import sys
import time
from pathlib import Path

import numpy as np

# Add parent directory to path to import audio_processing
sys.path.append(str(Path(__file__).parent.parent))

try:
    import soundfile as sf

    from audio_processing import AudioProcessor
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the correct environment with all dependencies installed")
    sys.exit(1)

def test_resemble_enhance_on_real_sermon():
    """Test Resemble Enhance processing on the Mark Hogan sermon"""

    print("🎵 Comprehensive Resemble Enhance Test on Real Sermon Audio")
    print("=" * 70)

    # Locate the audio file
    test_dir = Path(__file__).parent
    audio_file = test_dir / "2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3"

    if not audio_file.exists():
        print(f"❌ Audio file not found: {audio_file}")
        return False

    print(f"📁 Audio file: {audio_file.name}")

    # Get file info
    try:
        info = sf.info(str(audio_file))
        duration_minutes = info.frames / info.samplerate / 60
        print(f"📊 File info: {info.frames:,} samples, {info.samplerate} Hz, {duration_minutes:.2f} minutes")
        print(f"📊 Channels: {info.channels}, Format: {info.format}")
    except Exception as e:
        print(f"⚠️  Could not read file info: {e}")

    # Initialize processor with Resemble Enhance
    print("\n🔧 Initializing AudioProcessor with Resemble Enhance...")
    try:
        processor = AudioProcessor(enhancement_method="resemble_enhance")
        print(f"✅ Processor initialized with method: {processor.enhancement_method}")
    except Exception as e:
        print(f"❌ Failed to initialize processor: {e}")
        return False

    # Set up output file
    output_file = test_dir / f"{audio_file.stem}_resemble_enhanced.wav"
    print(f"📤 Output will be saved to: {output_file.name}")

    # Process the audio
    print("\n🎵 Processing audio with Resemble Enhance...")
    start_time = time.time()

    try:
        success = processor.process_sermon_audio(
            input_path=str(audio_file),
            output_path=str(output_file),
            noise_reduction=True,
            amplify=True,
            normalize=True,
            gain_db=3.0,
            max_duration_minutes=5  # Process only first 5 minutes for testing
        )

        processing_time = time.time() - start_time

        if success:
            print("✅ Processing completed successfully!")
            print(f"⏱️  Processing time: {processing_time:.2f} seconds")

            # Check output file
            if output_file.exists():
                try:
                    output_info = sf.info(str(output_file))
                    output_duration = output_info.frames / output_info.samplerate / 60
                    print(f"📊 Output file: {output_info.frames:,} samples, {output_info.samplerate} Hz")
                    print(f"📊 Output duration: {output_duration:.2f} minutes")

                    # Calculate file sizes
                    input_size = audio_file.stat().st_size / (1024 * 1024)  # MB
                    output_size = output_file.stat().st_size / (1024 * 1024)  # MB
                    print(f"📊 Input size: {input_size:.2f} MB")
                    print(f"📊 Output size: {output_size:.2f} MB")

                    # Quick audio analysis
                    audio_data, sr = sf.read(str(output_file))
                    if len(audio_data.shape) > 1:
                        audio_data = audio_data.mean(axis=1)  # Convert to mono if stereo

                    rms = np.sqrt(np.mean(audio_data**2))
                    peak = np.max(np.abs(audio_data))

                    print("🔊 Audio analysis:")
                    print(f"   - RMS level: {rms:.4f}")
                    print(f"   - Peak level: {peak:.4f}")
                    print(f"   - Dynamic range: {20 * np.log10(peak/rms):.1f} dB")

                except Exception as e:
                    print(f"⚠️  Could not analyze output file: {e}")

                print(f"✅ Output file created: {output_file}")
                return True
            else:
                print("❌ Output file was not created")
                return False
        else:
            print("❌ Processing failed")
            return False

    except Exception as e:
        processing_time = time.time() - start_time
        print(f"❌ Processing failed with exception: {e}")
        print(f"⏱️  Time before failure: {processing_time:.2f} seconds")
        return False

def test_resemble_vs_deepfilter_comparison():
    """Compare Resemble Enhance vs DeepFilterNet on a short audio sample"""

    print("\n🆚 Comparison Test: Resemble Enhance vs DeepFilterNet")
    print("=" * 70)

    test_dir = Path(__file__).parent
    audio_file = test_dir / "2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3"

    if not audio_file.exists():
        print(f"❌ Audio file not found: {audio_file}")
        return False

    # Test parameters
    max_duration = 1.0  # Process only 1 minute for comparison

    results = {}

    for method in ["resemble_enhance", "deepfilternet"]:
        print(f"\n🔧 Testing {method}...")

        try:
            processor = AudioProcessor(enhancement_method=method)
            output_file = test_dir / f"{audio_file.stem}_{method}_comparison.wav"

            start_time = time.time()
            success = processor.process_sermon_audio(
                input_path=str(audio_file),
                output_path=str(output_file),
                noise_reduction=True,
                amplify=False,
                normalize=False,
                max_duration_minutes=max_duration
            )
            processing_time = time.time() - start_time

            if success and output_file.exists():
                # Analyze output
                audio_data, sr = sf.read(str(output_file))
                if len(audio_data.shape) > 1:
                    audio_data = audio_data.mean(axis=1)

                rms = np.sqrt(np.mean(audio_data**2))
                peak = np.max(np.abs(audio_data))

                results[method] = {
                    'success': True,
                    'time': processing_time,
                    'rms': rms,
                    'peak': peak,
                    'file_size': output_file.stat().st_size / (1024 * 1024)
                }

                print(f"✅ {method}: {processing_time:.2f}s, RMS: {rms:.4f}, Peak: {peak:.4f}")
            else:
                results[method] = {'success': False, 'time': processing_time}
                print(f"❌ {method}: Failed after {processing_time:.2f}s")

        except Exception as e:
            print(f"❌ {method}: Exception - {e}")
            results[method] = {'success': False, 'error': str(e)}

    # Print comparison summary
    print("\n📊 Comparison Summary:")
    print("-" * 50)
    for method, result in results.items():
        if result['success']:
            print(f"{method:20s}: ✅ {result['time']:6.2f}s, RMS: {result['rms']:.4f}")
        else:
            print(f"{method:20s}: ❌ Failed")

    return True

def main():
    """Run all Resemble Enhance tests"""

    print("🚀 Starting Comprehensive Resemble Enhance Test Suite")
    print("=" * 70)

    # Test 1: Full Resemble Enhance test on real sermon
    print("Test 1: Resemble Enhance on Real Sermon (5 minutes)")
    test1_success = test_resemble_enhance_on_real_sermon()

    # Test 2: Comparison test
    print("Test 2: Method Comparison (1 minute)")
    test2_success = test_resemble_vs_deepfilter_comparison()

    # Summary
    print("\n🏁 Test Suite Summary")
    print("=" * 70)
    print(f"Test 1 (Real Sermon):     {'✅ PASSED' if test1_success else '❌ FAILED'}")
    print(f"Test 2 (Comparison):      {'✅ PASSED' if test2_success else '❌ FAILED'}")

    overall_success = test1_success and test2_success
    print(f"Overall Result:           {'✅ PASSED' if overall_success else '❌ FAILED'}")

    if not overall_success:
        print("\n⚠️  Note: Resemble Enhance may have Windows compatibility issues")
        print("   The fallback to custom noise reduction should still work")

    return overall_success

if __name__ == "__main__":
    main()
