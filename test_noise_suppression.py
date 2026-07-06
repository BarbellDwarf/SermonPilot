#!/usr/bin/env python3
"""Compare noise suppression: noisereduce TorchGate vs speechbrain SpectralMaskEnhancement"""

import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ui'))

import torch
import torchaudio
import numpy as np

INPUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_clip.mp3"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/tmp/noise_test"
os.makedirs(OUT_DIR, exist_ok=True)

print(f"Input: {INPUT}")
print(f"Output dir: {OUT_DIR}")
print(f"Torch: {torch.__version__}, CUDA: {torch.cuda.is_available()}")

device = "cuda" if torch.cuda.is_available() else "cpu"

# Load audio
waveform, sr = torchaudio.load(INPUT)
if waveform.shape[0] > 1:
    waveform = waveform.mean(dim=0, keepdim=True)
print(f"Audio: {waveform.shape}, sr={sr}, duration={waveform.shape[1]/sr:.1f}s")

# Save original as reference
torchaudio.save(os.path.join(OUT_DIR, "original.wav"), waveform, sr)

results = {}

# ====== 1. noisereduce TorchGate ======
print("\n--- noisereduce TorchGate ---")
try:
    from noisereduce.torchgate import TorchGate
    t0 = time.time()
    tg = TorchGate(sr=sr, nonstationary=True).to(device)
    wav = waveform.to(device)
    enhanced = tg(wav)
    t = time.time() - t0
    torchaudio.save(os.path.join(OUT_DIR, "noisereduce.wav"), enhanced.cpu(), sr)
    results['noisereduce'] = {'time_s': round(t, 2), 'device': device}
    print(f"  Done in {t:.2f}s")
except Exception as e:
    results['noisereduce'] = {'error': str(e)}
    print(f"  FAILED: {e}")

# ====== 2. speechbrain SpectralMaskEnhancement ======
print("\n--- speechbrain SpectralMaskEnhancement ---")
try:
    from speechbrain.inference.enhancement import SpectralMaskEnhancement
    t0 = time.time()
    enhancer = SpectralMaskEnhancement.from_hparams(
        source="speechbrain/metricgan-plus-voicebank",
        savedir=os.path.join(OUT_DIR, "model_cache"),
        run_opts={"device": device},
    )
    enhanced = enhancer.enhance_batch(waveform.to(device), lengths=torch.tensor([1.0]).to(device))
    t = time.time() - t0
    torchaudio.save(os.path.join(OUT_DIR, "speechbrain_metricgan.wav"), enhanced.cpu(), sr)
    results['speechbrain_metricgan'] = {'time_s': round(t, 2), 'device': device}
    print(f"  Done in {t:.2f}s")
except Exception as e:
    results['speechbrain_metricgan'] = {'error': str(e)}
    print(f"  FAILED: {e}")

# ====== 3. speechbrain WaveformEnhancement (if available) ======
print("\n--- speechbrain WaveformEnhancement ---")
try:
    from speechbrain.inference.enhancement import WaveformEnhancement
    t0 = time.time()
    enhancer = WaveformEnhancement.from_hparams(
        source="speechbrain/mtl-face-voice-enhancement",
        savedir=os.path.join(OUT_DIR, "model_cache"),
        run_opts={"device": device},
    )
    enhanced = enhancer.enhance_batch(waveform.to(device), lengths=torch.tensor([1.0]).to(device))
    t = time.time() - t0
    torchaudio.save(os.path.join(OUT_DIR, "speechbrain_waveform.wav"), enhanced.cpu(), sr)
    results['speechbrain_waveform'] = {'time_s': round(t, 2), 'device': device}
    print(f"  Done in {t:.2f}s")
except Exception as e:
    results['speechbrain_waveform'] = {'error': str(e)}
    print(f"  FAILED: {e}")

# ====== Summary ======
print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)
for name, r in results.items():
    if 'error' in r:
        print(f"  {name}: ERROR - {r['error']}")
    else:
        print(f"  {name}: {r['time_s']}s on {r['device']}")

print(f"\nOutput files in {OUT_DIR}:")
for f in sorted(os.listdir(OUT_DIR)):
    if f.endswith('.wav'):
        sz = os.path.getsize(os.path.join(OUT_DIR, f))
        print(f"  {f}: {sz/1024:.0f}KB")

with open(os.path.join(OUT_DIR, "results.json"), "w") as fp:
    json.dump(results, fp, indent=2)
print("\nDone.")
