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

import sys, json, argparse, shutil, subprocess
import numpy as np
import soundfile as sf

# Seed-VC resolves these from the Hugging Face repository when no checkpoint is
# passed. Recorded per job so a take can be reproduced against the same weights.
VOICE_CHECKPOINTS = {
    "speech": "DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth",
    "singing": "DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema_v2.pth",
}
# CPU is the portable baseline. mps is selected per machine after validating it.
DEFAULT_VOICE_DEVICE = "cpu"
DEFAULT_SEED = 1234
LENGTH_ADJUST = 1.0
INFERENCE_CFG_RATE = 0.7
# Both inputs are matched to this level so a quiet source or a hot reference
# stops changing the conversion.
NORMALISE_LUFS = -20.0
NORMALISE_PEAK = 0.95


def normalise_loudness(source, dest, target_lufs=NORMALISE_LUFS):
    """Write dest at target_lufs integrated, backing off rather than clipping."""
    import pyloudnorm as pyln
    audio, sr = sf.read(str(source), always_2d=True, dtype="float64")
    measured = pyln.Meter(sr).integrated_loudness(audio)
    gain = 10 ** ((target_lufs - measured) / 20) if np.isfinite(measured) else 1.0
    peak = float(np.max(np.abs(audio))) * gain
    if peak > NORMALISE_PEAK:
        gain *= NORMALISE_PEAK / peak
    sf.write(str(dest), audio * gain, sr, subtype="PCM_24")
    return {"measured_lufs": round(float(measured), 2) if np.isfinite(measured) else None,
            "applied_gain_db": round(20 * float(np.log10(max(gain, 1e-12))), 2)}


def run_voice(args, out):
    vendor = ROOT / "vendor" / "seed-vc"
    if not (vendor / "inference.py").exists():
        raise RuntimeError("Seed-VC is not installed. Run setup.command first.")
    device = os.environ.get("FORMA_VOICE_DEVICE") or DEFAULT_VOICE_DEVICE
    prepared = out / "prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    source, reference = prepared / "source.wav", prepared / "reference.wav"
    source_level = normalise_loudness(args.source, source)
    reference_level = normalise_loudness(args.reference, reference)

    # Seed-VC is GPL-3.0. Forma invokes it as a separate command-line program
    # rather than importing it, so the two code bases stay separable.
    command = [sys.executable, "-u", "inference.py",
               "--source", str(source.resolve()), "--target", str(reference.resolve()),
               "--output", str(out.resolve()),
               "--diffusion-steps", str(args.steps),
               "--length-adjust", str(LENGTH_ADJUST),
               "--inference-cfg-rate", str(INFERENCE_CFG_RATE),
               "--f0-condition", "True" if args.mode == "singing" else "False",
               "--auto-f0-adjust", "False",
               "--semi-tone-shift", str(args.pitch),
               "--fp16", "False",
               "--seed", str(args.seed)]
    environment = dict(os.environ)
    environment["FORMA_VOICE_DEVICE"] = device
    environment.setdefault("OMP_NUM_THREADS", str(min(4, os.cpu_count() or 2)))
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(vendor)] + ([environment["PYTHONPATH"]] if environment.get("PYTHONPATH") else []))
    print(f"Loading local Seed-VC models on {device}. First use downloads model weights.", flush=True)
    completed = subprocess.run(command, cwd=str(vendor), env=environment)
    if completed.returncode != 0:
        raise RuntimeError(f"Seed-VC inference exited with code {completed.returncode}")

    # inference.py names its file from the inputs and settings, so the result is
    # addressed directly instead of being picked out of a glob.
    produced = out / (f"vc_{source.stem}_{reference.stem}_{LENGTH_ADJUST}"
                      f"_{args.steps}_{INFERENCE_CFG_RATE}.wav")
    if not produced.is_file():
        raise RuntimeError("Voice engine returned no audio")
    produced.replace(out / "converted-voice.wav")
    shutil.rmtree(prepared, ignore_errors=True)
    (out / "analysis.json").write_text(json.dumps({
        "seed": args.seed, "steps": args.steps, "mode": args.mode, "pitch": args.pitch,
        "device": device, "checkpoint": VOICE_CHECKPOINTS[args.mode],
        "length_adjust": LENGTH_ADJUST, "inference_cfg_rate": INFERENCE_CFG_RATE,
        "normalise_lufs": NORMALISE_LUFS,
        "source_level": source_level, "reference_level": reference_level,
    }))
    print("Voice conversion complete", flush=True)


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
        run_voice(args, out)

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
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    run(p.parse_args())
