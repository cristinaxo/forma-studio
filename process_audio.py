"""One local job per process, releasing model memory when finished."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
os.environ.setdefault("TORCH_HOME", str(ROOT / ".models" / "torch"))
os.environ.setdefault("HF_HOME", str(ROOT / ".models" / "huggingface"))
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / ".models" / "numba"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".models" / "matplotlib"))
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import sys, json, argparse
import numpy as np
import soundfile as sf

def run(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if args.tool == "master":
        from audio_engine import master
        audio, sr = sf.read(args.source, always_2d=True)
        result, stats = master(audio, sr, args.preset, args.target)
        sf.write(out / "master.wav", result, sr, subtype="PCM_24")
        (out / "analysis.json").write_text(json.dumps(stats))
        print("Master complete", flush=True)
    elif args.tool == "stems":
        import torch
        import torchaudio
        from demucs.pretrained import get_model
        from demucs.apply import apply_model
        torch.set_num_threads(min(4, os.cpu_count() or 2))
        print("Loading local Demucs model. First use downloads the model weights.", flush=True)
        model = get_model("htdemucs")
        model.eval()
        audio, sr = sf.read(args.source, always_2d=True, dtype="float32")
        wav = torch.from_numpy(audio.T)
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        wav = torchaudio.functional.resample(wav, sr, model.samplerate)
        ref = wav.mean(0)
        mean, std = ref.mean(), ref.std().clamp_min(1e-8)
        wav = (wav - mean) / std
        print("Separating vocals, drums, bass and other instruments on this Mac…", flush=True)
        with torch.no_grad():
            result = apply_model(model, wav[None], device="cpu", shifts=0,
                                 split=True, overlap=.25, progress=True, num_workers=0)[0]
        result = result * std + mean
        # Shared gain preserves the balance between stems.
        result /= max(1.0, float(result.abs().max()) / .99)
        for name, samples in zip(model.sources, result):
            sf.write(out / f"{name}.wav", samples.T.numpy(), model.samplerate, subtype="PCM_24")
        print("All four stems are ready", flush=True)
    elif args.tool == "voice":
        import torch
        from types import SimpleNamespace
        vendor = ROOT / "vendor" / "seed-vc"
        if not (vendor / "inference.py").exists():
            raise RuntimeError("Seed-VC is not installed. Run setup.command first.")
        sys.path.insert(0, str(vendor))
        os.chdir(vendor)
        import inference
        # CPU is a reliable portable baseline; a tested GPU can be selected
        # explicitly without silently failing over mid-job.
        device = os.environ.get("FORMA_VOICE_DEVICE", "cpu")
        inference.device = torch.device(device)
        torch.set_num_threads(min(4, os.cpu_count() or 2))
        print("Loading local Seed-VC models. First use downloads model weights.", flush=True)
        inference.main(SimpleNamespace(
            source=str(Path(args.source).resolve()), target=str(Path(args.reference).resolve()),
            output=str(out.resolve()), diffusion_steps=args.steps, length_adjust=1.0,
            inference_cfg_rate=.7, f0_condition=args.mode == "singing", auto_f0_adjust=False,
            semi_tone_shift=args.pitch, checkpoint=None, config=None, fp16=False,
        ))
        files = list(out.glob("*.wav"))
        if not files:
            raise RuntimeError("Voice engine returned no audio")
        files[0].rename(out / "converted-voice.wav")
        print("Voice conversion complete", flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("tool", choices=["master", "stems", "voice"])
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--reference")
    p.add_argument("--preset", default="balanced")
    p.add_argument("--target", type=float, default=-14)
    p.add_argument("--steps", type=int, default=10)
    p.add_argument("--pitch", type=int, default=0)
    p.add_argument("--mode", choices=["speech", "singing"], default="speech")
    run(p.parse_args())
