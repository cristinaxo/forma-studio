"""Local mastering. No cloud calls, generated audio, or fabricated results."""
import numpy as np
from scipy import signal, ndimage
import pyloudnorm as pyln

PRESETS = {
    "balanced": {"bass": 0.8, "air": 1.0, "threshold": -18, "ratio": 2.0},
    "warm": {"bass": 2.0, "air": -0.8, "threshold": -20, "ratio": 2.5},
    "bright": {"bass": -0.5, "air": 2.5, "threshold": -18, "ratio": 2.0},
    "punch": {"bass": 1.5, "air": 1.5, "threshold": -16, "ratio": 3.0},
}

def peak_eq(audio, sr, hz, gain, q=0.7):
    a = 10 ** (gain / 40)
    w = 2 * np.pi * hz / sr
    alpha = np.sin(w) / (2 * q)
    b = [1 + alpha * a, -2 * np.cos(w), 1 - alpha * a]
    c = [1 + alpha / a, -2 * np.cos(w), 1 - alpha / a]
    return signal.lfilter(np.array(b) / c[0], np.array(c) / c[0], audio, axis=0)

def loudness(audio, sr):
    value = pyln.Meter(sr).integrated_loudness(audio)
    return round(float(value), 2) if np.isfinite(value) else None

def master(audio, sr, preset="balanced", target=-14):
    if preset not in PRESETS or not -20 <= target <= -9:
        raise ValueError("Invalid mastering settings")
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.shape[1] > 2 or len(x) < int(sr * 0.5) or not np.isfinite(x).all():
        raise ValueError("Use a valid mono or stereo clip at least 0.5 seconds long")
    before = loudness(x, sr)
    if before is None:
        raise ValueError("This file is silent. Choose a recording with audible content.")
    p = PRESETS[preset]
    x = signal.sosfilt(signal.butter(2, 25, "highpass", fs=sr, output="sos"), x, axis=0)
    x = peak_eq(x, sr, 120, p["bass"])
    x = peak_eq(x, sr, min(7500, sr * 0.35), p["air"], 0.5)
    # Stereo-linked smoothed level detector, 25 ms RMS window.
    power = ndimage.uniform_filter1d(np.max(x * x, axis=1), max(1, int(sr * .025)))
    level_db = 10 * np.log10(np.maximum(power, 1e-12))
    reduction = np.maximum(level_db - p["threshold"], 0) * (1 - 1 / p["ratio"])
    reduction = ndimage.gaussian_filter1d(reduction, max(1, int(sr * .004)))
    x *= (10 ** (-reduction / 20))[:, None]
    current = loudness(x, sr)
    x *= 10 ** (min(target - current, 24) / 20)
    # Offline lookahead peak limiter. A final 4x oversampled peak check
    # controls intersample overshoot. Loudness is reported, never promised.
    ceiling = 10 ** (-1 / 20)
    envelope = ndimage.maximum_filter1d(np.max(np.abs(x), axis=1), max(3, int(sr * .01) | 1))
    gain = np.minimum(1, ceiling / np.maximum(envelope, 1e-12))
    x *= gain[:, None]
    peak = float(np.max(np.abs(signal.resample_poly(x, 4, 1, axis=0))))
    if peak > ceiling:
        x *= ceiling / peak
    true_peak = float(np.max(np.abs(signal.resample_poly(x, 4, 1, axis=0))))
    return x.astype(np.float32), {
        "input_lufs": before, "output_lufs": loudness(x, sr),
        "target_lufs": target, "true_peak_dbtp": round(20 * np.log10(max(true_peak, 1e-12)), 2),
        "preset": preset,
    }
