#!/usr/bin/env python3
"""
Test script for Resemble Enhance with real audio files
"""

import os
import sys
import time

import numpy as np
import soundfile as sf

# Add current directory to path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Add src directory to path
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_processing import AudioProcessor


def test_resemble_enhance_real_audio():
    """Test Resemble Enhance with real sermon audio"""
    print("=" * 60)
    print("Resemble Enhance Real Audio Test")
    print("=" * 60)

    # Find available audio files in tests folder
    test_files = []
    tests_dir = os.path.join(os.path.dirname(__file__), "tests")

    if os.path.exists(tests_dir):
        for file in os.listdir(tests_dir):
            if file.lower().endswith(('.mp3', '.wav', '.m4a', '.flac')):
                test_files.append(os.path.join(tests_dir, file))

    if not test_files:
        print("❌ No audio files found in tests folder")
        return False

    # Use the first audio file found
    input_file = test_files[0]
    print(f"📁 Using audio file: {os.path.basename(input_file)}")

    # Get file info
    try:
        info = sf.info(input_file)
        duration_minutes = info.frames / info.samplerate / 60
        print(f"📊 File info: {info.frames:,} samples, {info.samplerate} Hz, {duration_minutes:.2f} minutes")
        print(f"📊 Channels: {info.channels}, Format: {info.format}")
    except Exception as e:
        print(f"❌ Could not read file info: {e}")
        return False

    # Create output filename
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = f"{base_name}_resemble_enhanced.wav"
    output_path = os.path.join(os.path.dirname(__file__), output_file)

    try:
        print("\n🔧 Initializing audio processor with Resemble Enhance...")
        processor = AudioProcessor(enhancement_method="resemble_enhance")
        print(f"✅ Audio processor initialized with method: {processor.enhancement_method}")

        print(f"\n🎵 Processing audio: {os.path.basename(input_file)}")
        print(f"📤 Output will be saved to: {os.path.basename(output_path)}")

        # Start timing
        start_time = time.time()

        # Process the audio with Resemble Enhance
        success = processor.process_sermon_audio(
            input_file,
            output_path,
            noise_reduction=True,  # Enable noise reduction
            amplify=False,         # Disable amplification to focus on enhancement
            normalize=False        # Disable normalization to preserve dynamics
        )

        # End timing
        end_time = time.time()
        processing_time = end_time - start_time

        if success:
            print("✅ Audio processing completed successfully!")
            print(f"⏱️  Processing time: {processing_time:.2f} seconds ({processing_time/60:.2f} minutes)")

            # Get output file info
            if os.path.exists(output_path):
                output_info = sf.info(output_path)
                output_duration = output_info.frames / output_info.samplerate / 60
                print(f"📊 Output info: {output_info.frames:,} samples, {output_info.samplerate} Hz, {output_duration:.2f} minutes")

                # Calculate processing speed
                speed_ratio = duration_minutes / (processing_time / 60)
                print(f"🚀 Processing speed: {speed_ratio:.2f}x real-time")

                # Read a sample of the audio to verify it's valid
                try:
                    sample_data, sample_rate = sf.read(output_path, frames=44100)  # Read first second
                    rms = np.sqrt(np.mean(sample_data**2))
                    print(f"🔊 Output audio RMS level: {rms:.4f}")

                    if rms > 0.001:  # Reasonable audio level
                        print("✅ Output audio appears to be valid (non-silent)")
                    else:
                        print("⚠️  Output audio may be very quiet or silent")

                except Exception as e:
                    print(f"⚠️  Could not verify output audio: {e}")

                print(f"\n🎯 Enhanced audio saved to: {output_path}")
                return True
            else:
                print("❌ Output file was not created")
                return False
        else:
            print("❌ Audio processing failed")
            return False

    except Exception as e:
        print(f"❌ Error during processing: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_comparison_processing():
    """Test both DeepFilterNet and Resemble Enhance for comparison"""
    print("\n" + "=" * 60)
    print("Comparison Test: DeepFilterNet vs Resemble Enhance")
    print("=" * 60)

    # Find audio file
    tests_dir = os.path.join(os.path.dirname(__file__), "tests")
    test_files = []

    if os.path.exists(tests_dir):
        for file in os.listdir(tests_dir):
            if file.lower().endswith(('.mp3', '.wav', '.m4a', '.flac')):
                test_files.append(os.path.join(tests_dir, file))

    if not test_files:
        print("❌ No audio files found for comparison")
        return False

    input_file = test_files[0]
    base_name = os.path.splitext(os.path.basename(input_file))[0]

    # Test both methods
    methods = [
        ("deepfilternet", f"{base_name}_deepfilternet.wav"),
        ("resemble_enhance", f"{base_name}_resemble_enhance.wav")
    ]

    results = {}

    for method, output_file in methods:
        print(f"\n🔄 Testing {method.upper()}...")
        output_path = os.path.join(os.path.dirname(__file__), output_file)

        try:
            processor = AudioProcessor(enhancement_method=method)
            start_time = time.time()

            success = processor.process_sermon_audio(
                input_file,
                output_path,
                noise_reduction=True,
                amplify=False,
                normalize=False
            )

            end_time = time.time()
            processing_time = end_time - start_time

            if success and os.path.exists(output_path):
                # Get file size
                file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB

                # Get audio info
                info = sf.info(output_path)
                duration = info.frames / info.samplerate / 60

                results[method] = {
                    'success': True,
                    'time': processing_time,
                    'file_size': file_size,
                    'duration': duration,
                    'output_path': output_path
                }

                print(f"✅ {method} completed in {processing_time:.2f}s")
                print(f"📁 Output: {file_size:.2f} MB, {duration:.2f} min")
            else:
                results[method] = {'success': False}
                print(f"❌ {method} failed")

        except Exception as e:
            results[method] = {'success': False, 'error': str(e)}
            print(f"❌ {method} error: {e}")

    # Summary
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")

    for method, result in results.items():
        if result.get('success'):
            print(f"{method.upper()}:")
            print(f"  ⏱️  Time: {result['time']:.2f} seconds")
            print(f"  📁 Size: {result['file_size']:.2f} MB")
            print(f"  🎵 Duration: {result['duration']:.2f} minutes")
            print(f"  🚀 Speed: {result['duration'] / (result['time'] / 60):.2f}x real-time")
        else:
            print(f"{method.upper()}: ❌ FAILED")

    return any(result.get('success', False) for result in results.values())

if __name__ == "__main__":
    print("🎵 Testing Resemble Enhance with real audio files...")

    # Test 1: Basic Resemble Enhance processing
    test1_success = test_resemble_enhance_real_audio()

    # Test 2: Comparison between methods
    test2_success = test_comparison_processing()

    print(f"\n{'='*60}")
    print("FINAL RESULTS")
    print(f"{'='*60}")
    print(f"Resemble Enhance Test: {'✅ PASSED' if test1_success else '❌ FAILED'}")
    print(f"Comparison Test: {'✅ PASSED' if test2_success else '❌ FAILED'}")

    if test1_success or test2_success:
        print("\n🎉 At least one test passed! Resemble Enhance is working.")
    else:
        print("\n❌ All tests failed. Check the error messages above.")

    print(f"{'='*60}")
