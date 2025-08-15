#!/usr/bin/env python

"""
Test script for DeepFilterNet with GPU support.
This script tests DeepFilterNet's ability to process a small audio sample.
"""

import logging
import os
import sys

import numpy as np
import soundfile as sf

# Show Python path information for debugging
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

# Try different import strategies for DeepFilterNet
try:
    import torch
    print(f"PyTorch version: {torch.__version__}")

    # Try direct import
    try:
        from deepfilternet import DeepFilterNet
        print("Successfully imported DeepFilterNet directly")
    except ImportError as e1:
        print(f"Failed to import deepfilternet directly: {e1}")

        # Try importing from df package
        try:
            from df import enhance, init_df
            print("Successfully imported DeepFilterNet via df package")
            # We'll need to use init_df() instead of DeepFilterNet.get_model()
            DeepFilterNet = None
        except ImportError as e2:
            print(f"Failed to import df package: {e2}")
            print("No DeepFilterNet implementation found")
            raise ImportError("DeepFilterNet is required but not available")
except ImportError as e:
    print(f"Failed to import torch: {e}")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_deepfilter():
    """Test DeepFilterNet on a small audio file."""

    # Check if CUDA is available
    logger.info(f"PyTorch version: {torch.__version__}")
    logger.info(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"CUDA device: {torch.cuda.get_device_name(0)}")
        device = "cuda"
    else:
        logger.info("CUDA not available, using CPU")
        device = "cpu"

    # Try to initialize DeepFilterNet
    try:
        if DeepFilterNet is not None:
            # Use new DeepFilterNet API
            logger.info(f"Initializing DeepFilterNet on {device}")
            df_filter = DeepFilterNet.get_model(device=device)
            use_new_api = True
        else:
            # Use legacy df API
            logger.info("Initializing DeepFilterNet with legacy API")
            df_model, df_state, _ = init_df()
            use_new_api = False
        logger.info("DeepFilterNet initialization successful")
    except Exception as e:
        logger.error(f"Failed to initialize DeepFilterNet: {e}")
        return False

    # Test audio processing
    try:
        # Find available audio file for testing
        audio_files = [f for f in os.listdir('.') if f.endswith('.mp3')]
        if not audio_files:
            logger.error("No audio files found for testing")
            return False

        test_file = audio_files[0]
        logger.info(f"Testing with audio file: {test_file}")

        # Load audio with fixed frame count (10 seconds at 44.1kHz)
        sample_rate = 44100  # Default sample rate
        frames = sample_rate * 10  # 10 seconds of audio
        data, sr = sf.read(test_file, frames=frames)
        sample_rate = sr  # Use the actual sample rate from the file
        logger.info(f"Loaded audio: {len(data)} samples at {sample_rate} Hz")

        # Process with DeepFilterNet
        logger.info("Processing with DeepFilterNet...")
        if data.dtype != np.float32:
            data = data.astype(np.float32)

        # Process audio based on which API we're using
        if use_new_api:
            processed = df_filter.process_audio(data, sample_rate)
        else:
            processed = enhance(df_model, df_state, data)

        # Save result
        output_file = "test_deepfilter_output.wav"
        sf.write(output_file, processed, sample_rate)
        logger.info(f"Processed audio saved to {output_file}")

        return True
    except Exception as e:
        logger.error(f"DeepFilterNet processing failed: {e}")
        return False

if __name__ == "__main__":
    success = test_deepfilter()
    if success:
        print("DeepFilterNet test completed successfully")
    else:
        print("DeepFilterNet test failed")
