#!/usr/bin/env python3
"""
Quick test for fixed Resemble Enhance Python API
"""

import os
import sys
import time

import numpy as np
import soundfile as sf

# Add current directory to path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from audio_processing import AudioProcessor


def test_quick_resemble_enhance():
    """Quick test with small audio segment"""
    print("🔧 Testing fixed Resemble Enhance Python API...")

    # Create a small test audio (5 seconds)
    sample_rate = 44100
    duration = 5  # seconds
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Clean signal (sine wave)
    clean_signal = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz tone

    # Add noise
    noise = 0.1 * np.random.randn(len(clean_signal))
    noisy_signal = clean_signal + noise

    # Save test file
    test_input = "test_quick_noisy.wav"
    test_output = "test_quick_enhanced.wav"

    try:
        sf.write(test_input, noisy_signal, sample_rate)
        print(f"✅ Created test audio: {test_input}")

        # Initialize processor
        processor = AudioProcessor(enhancement_method="resemble_enhance")

        # Process
        start_time = time.time()
        success = processor.process_sermon_audio(
            test_input,
            test_output,
            noise_reduction=True,
            amplify=False,
            normalize=False
        )
        end_time = time.time()

        if success and os.path.exists(test_output):
            # Verify output
            enhanced_data, _ = sf.read(test_output)
            rms = np.sqrt(np.mean(enhanced_data**2))
            print("✅ Enhancement successful!")
            print(f"⏱️  Processing time: {end_time - start_time:.2f} seconds")
            print(f"🔊 Output RMS: {rms:.4f}")

            # Cleanup
            os.remove(test_input)
            os.remove(test_output)
            return True
        else:
            print("❌ Enhancement failed")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_quick_resemble_enhance()
    print(f"\nResult: {'✅ SUCCESS' if success else '❌ FAILED'}")
