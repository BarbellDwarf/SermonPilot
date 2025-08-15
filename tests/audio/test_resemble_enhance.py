#!/usr/bin/env python3
"""
Test script for Resemble Enhance integration
"""

import os
import sys
import tempfile

import numpy as np
import soundfile as sf

# Add current directory to path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from audio_processing import AudioProcessor


def test_resemble_enhance():
    """Test Resemble Enhance functionality"""
    print("Testing Resemble Enhance integration...")

    # Create a simple test audio signal (sine wave with noise)
    sample_rate = 44100
    duration = 2.0  # 2 seconds
    frequency = 440  # A4 note

    # Generate clean sine wave
    t = np.linspace(0, duration, int(sample_rate * duration))
    clean_signal = 0.5 * np.sin(2 * np.pi * frequency * t)

    # Add some noise
    noise = 0.1 * np.random.randn(len(clean_signal))
    noisy_signal = clean_signal + noise

    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_input:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
            try:
                # Write noisy audio
                sf.write(temp_input.name, noisy_signal.astype(np.float32), sample_rate)
                print(f"Created test audio: {temp_input.name}")

                # Initialize audio processor with Resemble Enhance
                processor = AudioProcessor(enhancement_method="resemble_enhance")
                print(f"Audio processor initialized with method: {processor.enhancement_method}")

                # Process the audio
                print("Processing audio...")
                success = processor.process_sermon_audio(
                    temp_input.name,
                    temp_output.name,
                    noise_reduction=True,
                    amplify=False,
                    normalize=False
                )

                if success:
                    print("✅ Audio processing completed successfully!")

                    # Read processed audio
                    processed_audio, _ = sf.read(temp_output.name)
                    print(f"Original audio length: {len(noisy_signal)} samples")
                    print(f"Processed audio length: {len(processed_audio)} samples")

                    # Basic quality check
                    original_rms = np.sqrt(np.mean(noisy_signal**2))
                    processed_rms = np.sqrt(np.mean(processed_audio**2))
                    print(f"Original RMS: {original_rms:.4f}")
                    print(f"Processed RMS: {processed_rms:.4f}")

                    return True
                else:
                    print("❌ Audio processing failed")
                    return False

            except Exception as e:
                print(f"❌ Error during testing: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                # Clean up
                try:
                    os.unlink(temp_input.name)
                    os.unlink(temp_output.name)
                except:
                    pass

def test_imports():
    """Test that all required imports work"""
    print("Testing imports...")

    try:
        from resemble_enhance.enhancer.inference import denoise, enhance
        print("✅ Resemble Enhance Python API imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import Resemble Enhance Python API: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Resemble Enhance Integration Test")
    print("=" * 50)

    # Test imports first
    imports_ok = test_imports()

    if imports_ok:
        # Test actual processing
        processing_ok = test_resemble_enhance()

        if processing_ok:
            print("\n🎉 All tests passed! Resemble Enhance is working.")
        else:
            print("\n❌ Processing test failed.")
    else:
        print("\n❌ Import test failed. Resemble Enhance may not be properly installed.")

    print("=" * 50)
