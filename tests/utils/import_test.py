#!/usr/bin/env python

"""
Simple test script to verify DeepFilterNet import paths.
"""

import os
import sys

print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")
print(f"Current working directory: {os.getcwd()}")

print("\nTrying to import torch...")
try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    print(f"PyTorch installation path: {torch.__file__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA device: {torch.cuda.get_device_name(0)}")
except ImportError as e:
    print(f"Failed to import torch: {e}")

print("\nTrying to import torchaudio...")
try:
    import torchaudio
    print(f"TorchAudio version: {torchaudio.__version__}")
    print(f"TorchAudio installation path: {torchaudio.__file__}")
except ImportError as e:
    print(f"Failed to import torchaudio: {e}")

print("\nTrying to import from deepfilternet...")
try:
    from deepfilternet import DeepFilterNet
    print("Successfully imported DeepFilterNet from deepfilternet")
    print(f"DeepFilterNet path: {DeepFilterNet.__module__}")
    # Try to initialize
    print("Trying to initialize DeepFilterNet...")
    model = DeepFilterNet.get_model(device="cpu")
    print(f"Successfully initialized DeepFilterNet model: {model}")
except ImportError as e:
    print(f"Failed to import from deepfilternet: {e}")
except Exception as e:
    print(f"Error initializing DeepFilterNet: {e}")

print("\nTrying to import from df...")
try:
    from df import enhance, init_df
    print("Successfully imported enhance and init_df from df")
    # Try to initialize
    print("Trying to initialize DeepFilterNet with init_df...")
    model, state, _ = init_df()
    print("Successfully initialized DeepFilterNet with init_df")
except ImportError as e:
    print(f"Failed to import from df: {e}")
except Exception as e:
    print(f"Error initializing DeepFilterNet with init_df: {e}")

print("\nListing installed packages...")
try:
    import pkg_resources
    for package in pkg_resources.working_set:
        if 'deep' in package.key or 'torch' in package.key:
            print(f"  {package.key}=={package.version}")
except Exception as e:
    print(f"Error listing packages: {e}")
