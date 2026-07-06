#!/usr/bin/env python3
"""Test DeepFilterNet on the 48kHz test clip"""

import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ui'))

import torch
import torchaudio
import numpy as np

INPUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_clip_48k.wav"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/tmp/noise_test_48k"
os.makedirs(OUT_DIR, exist_ok=True)

print(f"Input: {INPUT}")
print(f"Output dir: {OUT_DIR}")

device = "cuda" if torch.cuda.is_available() else "cpu"

waveform, sr = torchaudio.load(INPUT)
if waveform.shape[0] > 1:
    waveform = waveform.mean(dim=0, keepdim=True)
print(f"Audio: {waveform.shape}, sr={sr}, duration={waveform.shape[1]/sr:.1f}s")

# DeepFilterNet
print("\n--- DeepFilterNet ---")
try:
    from df.enhance import enhance, init_df
    t0 = time.time()
    model, df_state, _ = init_df()
    enhanced = enhance(model, df_state, waveform.to(device))
    t = time.time() - t0
    if isinstance(enhanced, torch.Tensor):
        torchaudio.save(os.path.join(OUT_DIR, "deepfilternet.wav"), enhanced.cpu(), sr)
    else:
        torchaudio.save(os.path.join(OUT_DIR, "deepfilternet.wav"), torch.from_numpy(enhanced).unsqueeze(0).float(), sr)
    print(f"  Done in {t:.2f}s")
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback
    traceback.print_exc()

print("\nDone.")
