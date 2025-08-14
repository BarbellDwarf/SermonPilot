#!/usr/bin/env python3
"""Test script to measure actual DeepFilterNet memory usage"""


import numpy as np
import psutil
import torch


def print_memory_usage(stage):
    """Print current memory usage"""
    if torch.cuda.is_available():
        gpu_allocated = torch.cuda.memory_allocated(0) / (1024**3)
        gpu_reserved = torch.cuda.memory_reserved(0) / (1024**3)
        print(f"{stage}:")
        print(f"  GPU allocated: {gpu_allocated:.2f} GB")
        print(f"  GPU reserved: {gpu_reserved:.2f} GB")

    ram = psutil.virtual_memory()
    print(f"  System RAM used: {(ram.total - ram.available) / (1024**3):.1f} GB / {ram.total / (1024**3):.1f} GB")
    print()

def main():
    print("=== DeepFilterNet Memory Usage Test ===\n")

    # Initial state
    print_memory_usage("Initial state")

    # Load DeepFilterNet
    print("Loading DeepFilterNet...")
    try:
        from df.enhance import enhance, init_df
        print_memory_usage("After importing DeepFilterNet")

        # Initialize model
        model, df_state, _ = init_df()
        print_memory_usage("After loading DeepFilterNet model")

        # Test with different audio lengths
        sample_rate = 44100
        for duration_minutes in [1, 5, 10, 30, 45, 60]:
            duration_seconds = duration_minutes * 60
            samples = int(duration_seconds * sample_rate)

            print(f"Testing with {duration_minutes}-minute audio ({samples:,} samples)...")

            # Create test audio data
            audio_data = np.random.randn(1, samples).astype(np.float32)
            audio_tensor = torch.from_numpy(audio_data).cuda()

            print_memory_usage(f"After loading {duration_minutes}min audio to GPU")

            # Process the audio
            try:
                with torch.no_grad():
                    enhanced = enhance(model, df_state, audio_tensor)
                print_memory_usage(f"After processing {duration_minutes}min audio")

                # Clean up
                del audio_tensor, enhanced
                torch.cuda.empty_cache()
                print_memory_usage("After cleanup")

            except RuntimeError as e:
                if "out of memory" in str(e):
                    print(f"  ❌ OOM error with {duration_minutes}-minute audio")
                    print(f"  Error details: {e}")
                    torch.cuda.empty_cache()
                else:
                    print(f"  ❌ Runtime error: {e}")
                    torch.cuda.empty_cache()
            except Exception as e:
                print(f"  ❌ Other error: {e}")
                torch.cuda.empty_cache()

            print("-" * 50)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
