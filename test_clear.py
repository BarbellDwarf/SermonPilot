#!/usr/bin/env python3
"""Test Clear (desert-ant-labs) noise suppression on the 48kHz test clip"""

import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import torch
import torchaudio

INPUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_clip_48k.wav"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/tmp/noise_test_48k"
os.makedirs(OUT_DIR, exist_ok=True)

print(f"Input: {INPUT}")
print(f"Output dir: {OUT_DIR}")

waveform, sr = torchaudio.load(INPUT)
if waveform.shape[0] > 1:
    waveform = waveform.mean(dim=0, keepdim=True)
print(f"Audio: {waveform.shape}, sr={sr}, duration={waveform.shape[1]/sr:.1f}s")

print("\n--- Clear (desert-ant-labs) ---")
try:
    from huggingface_hub import hf_hub_download
    import onnxruntime as ort
    from df.enhance import init_df, df_features, as_complex
    from df.utils import get_device

    t0 = time.time()
    model_path = hf_hub_download("desert-ant-labs/clear", "clear-studio.onnx")
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    print(f"  Model loaded in {time.time()-t0:.2f}s")

    model_df, df_state, _ = init_df()
    device = get_device()
    n_fft = df_state.fft_size()
    hop = df_state.hop_size()
    nb_df = getattr(model_df, "nb_df", getattr(model_df, "df_bins", 32))

    audio_t = torch.nn.functional.pad(waveform.to(device), (0, n_fft))
    spec, erb_feat, spec_feat = df_features(audio_t, df_state, nb_df, device=device)

    n_frames = spec.shape[2]
    chunk_size = 200
    enhanced_frames = []

    t_infer = time.time()
    for start in range(0, n_frames, chunk_size):
        end = min(start + chunk_size, n_frames)
        spec_chunk = spec[:, :, start:end].cpu().numpy().astype(np.float32)
        erb_chunk = erb_feat[:, :, start:end].cpu().numpy().astype(np.float32)
        spec_feat_chunk = spec_feat[:, :, start:end].cpu().numpy().astype(np.float32)

        # Pad last chunk to 200 frames if needed
        if spec_chunk.shape[2] < chunk_size:
            pad = chunk_size - spec_chunk.shape[2]
            spec_chunk = np.pad(spec_chunk, ((0,0),(0,0),(0,pad),(0,0),(0,0)))
            erb_chunk = np.pad(erb_chunk, ((0,0),(0,0),(0,pad),(0,0)))
            spec_feat_chunk = np.pad(spec_feat_chunk, ((0,0),(0,0),(0,pad),(0,0),(0,0)))

        out = session.run(None, {
            "spec": spec_chunk,
            "feat_erb": erb_chunk,
            "feat_spec": spec_feat_chunk,
        })
        result = torch.from_numpy(out[0])
        # Trim padding
        if spec_chunk.shape[2] > end - start:
            result = result[:, :, :end-start]
        enhanced_frames.append(result)

    t_infer = time.time() - t_infer
    spec_enhanced = torch.cat(enhanced_frames, dim=2)

    enhanced_complex = as_complex(spec_enhanced.squeeze(1))
    audio_out = torch.as_tensor(df_state.synthesis(enhanced_complex.numpy()))
    d = n_fft - hop
    audio_out = audio_out[..., d:-d]

    t_total = time.time() - t0
    print(f"  audio_out shape: {audio_out.shape}")
    if audio_out.dim() == 1:
        audio_out = audio_out.unsqueeze(0)
    elif audio_out.dim() == 3:
        audio_out = audio_out.squeeze(0)
    torchaudio.save(os.path.join(OUT_DIR, "clear.wav"), audio_out.cpu(), sr)
    print(f"  Inference: {t_infer:.2f}s, Total: {t_total:.2f}s")

except Exception as e:
    print(f"  FAILED: {e}")
    import traceback
    traceback.print_exc()

print("\nDone.")
