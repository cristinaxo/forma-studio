"""Local mastering. No cloud calls, generated audio, or fabricated results.

The chain is: 25 Hz high-pass, 120 Hz bell, high-shelf air, stereo-linked
compressor with a real attack/release envelope follower, then a lookahead
peak limiter that measures its own peaks on a 4x oversampled signal so
intersample overshoot is controlled inside the limiter rather than by a
global trim afterwards. A loudness loop raises pre-gain and re-limits while
the target is still out of reach and the limiter is not working too hard.
Every number reported in the result is measured on the audio that is
returned.
"""
import numpy as np
from scipy import signal, ndimage
import pyloudnorm as pyln

try:  # numba ships with librosa; the loops below are the only hot spots.
    from numba import njit
except ImportError:  # pragma: no cover - pure-Python fallback, much slower
    def njit(**_kwargs):
        return lambda func: func

PRESETS = {
    "balanced": {"bass": 0.8, "air": 1.0, "threshold": -18, "ratio": 2.0,
                 "attack_ms": 20.0, "release_ms": 180.0, "limiter_release_ms": 100.0},
    "warm": {"bass": 2.0, "air": -0.8, "threshold": -20, "ratio": 2.5,
             "attack_ms": 30.0, "release_ms": 250.0, "limiter_release_ms": 150.0},
    "bright": {"bass": -0.5, "air": 2.5, "threshold": -18, "ratio": 2.0,
               "attack_ms": 15.0, "release_ms": 150.0, "limiter_release_ms": 80.0},
    "punch": {"bass": 1.5, "air": 1.5, "threshold": -16, "ratio": 3.0,
              "attack_ms": 10.0, "release_ms": 100.0, "limiter_release_ms": 50.0},
}

CEILING_DBTP = -1.0
# The limiter aims a little under the ceiling so the measured true peak of the
# gain-modulated output still lands at or below CEILING_DBTP.
LIMITER_HEADROOM_DB = 0.05
LOOKAHEAD_MS = 5.0
# Hard bound on how fast the limiter gain may move, in dB per sample. The
# lookahead window is widened when a signal would otherwise demand a faster
# move, which keeps the gain curve smooth instead of stepping.
MAX_GAIN_SLEW_DB = 0.08
OVERSAMPLE = 4
LOUDNESS_TOLERANCE_LU = 0.3
MAX_LIMITER_REDUCTION_DB = 6.0
MAX_LOUDNESS_PASSES = 4
MAX_PRE_GAIN_DB = 30.0


def peak_eq(audio, sr, hz, gain, q=0.7):
    """RBJ cookbook peaking EQ."""
    a = 10 ** (gain / 40)
    w = 2 * np.pi * hz / sr
    alpha = np.sin(w) / (2 * q)
    b = [1 + alpha * a, -2 * np.cos(w), 1 - alpha * a]
    c = [1 + alpha / a, -2 * np.cos(w), 1 - alpha / a]
    return signal.lfilter(np.array(b) / c[0], np.array(c) / c[0], audio, axis=0)


def high_shelf(audio, sr, hz, gain, slope=1.0):
    """RBJ cookbook high shelf. Lifts or trims everything above the corner."""
    a = 10 ** (gain / 40)
    w = 2 * np.pi * hz / sr
    cos_w = np.cos(w)
    alpha = np.sin(w) / 2 * np.sqrt((a + 1 / a) * (1 / slope - 1) + 2)
    sqrt_a = 2 * np.sqrt(a) * alpha
    b = np.array([a * ((a + 1) + (a - 1) * cos_w + sqrt_a),
                  -2 * a * ((a - 1) + (a + 1) * cos_w),
                  a * ((a + 1) + (a - 1) * cos_w - sqrt_a)])
    c = np.array([(a + 1) - (a - 1) * cos_w + sqrt_a,
                  2 * ((a - 1) - (a + 1) * cos_w),
                  (a + 1) - (a - 1) * cos_w - sqrt_a])
    return signal.lfilter(b / c[0], c / c[0], audio, axis=0)


def loudness(audio, sr):
    value = pyln.Meter(sr).integrated_loudness(audio)
    return round(float(value), 2) if np.isfinite(value) else None


def _coefficient(ms, sr):
    """One-pole coefficient for a time constant in milliseconds."""
    return float(1 - np.exp(-1.0 / max(1e-6, ms / 1000.0 * sr)))


@njit(cache=True)
def _follow(target, attack, release):
    """Attack/release envelope follower over a target gain-reduction curve."""
    out = np.empty_like(target)
    previous = 0.0
    for i in range(target.shape[0]):
        value = target[i]
        coefficient = attack if value > previous else release
        previous += (value - previous) * coefficient
        out[i] = previous
    return out


@njit(cache=True)
def _release_curve(attack_db, release):
    """Follow the lookahead ramp down instantly, recover on a one-pole curve.

    attack_db is the required gain in dB (never above 0) already ramped across
    the lookahead window, so following it downwards cannot step. Upwards the
    gain recovers on a one-pole curve in the dB domain and is clamped to the
    requirement, so the limiter never overshoots the ceiling.
    """
    out = np.empty_like(attack_db)
    previous = 0.0
    for i in range(attack_db.shape[0]):
        required = attack_db[i]
        if required <= previous:
            previous = required
        else:
            previous += (required - previous) * release
        out[i] = previous
    return out


def _forward_running_min(values, span):
    """Minimum of values[i : i + span], treating samples past the end as 0 dB."""
    n = values.shape[0]
    blocks = -(-n // span)
    padded = np.zeros(blocks * span + span, dtype=np.float64)
    padded[:n] = values
    body = padded[:blocks * span].reshape(blocks, span)
    suffix = np.minimum.accumulate(body[:, ::-1], axis=1)[:, ::-1].ravel()
    prefix = np.minimum.accumulate(body, axis=1).ravel()
    prefix = np.concatenate([prefix, np.zeros(span, dtype=np.float64)])
    return np.minimum(suffix[:n], prefix[span - 1:span - 1 + n])


def _oversampled_abs(x):
    """Per-oversample-index magnitude across channels, at OVERSAMPLE x sr."""
    peak = None
    for channel in range(x.shape[1]):
        up = signal.resample_poly(np.ascontiguousarray(x[:, channel], dtype=np.float32),
                                  OVERSAMPLE, 1)
        up = np.abs(up)
        peak = up if peak is None else np.maximum(peak, up, out=peak)
    return peak


def _oversampled_peak_db(x):
    """True-peak magnitude in dB per base-rate sample, from a 4x oversample."""
    n = x.shape[0]
    peak = _oversampled_abs(x)[:n * OVERSAMPLE].reshape(n, OVERSAMPLE).max(axis=1)
    return 20 * np.log10(np.maximum(peak.astype(np.float64), 1e-12))


def _true_peak_dbtp(x):
    return 20 * np.log10(max(float(np.max(_oversampled_abs(x))), 1e-12))


def _limiter_gain_db(peak_db, sr, release_ms, ceiling_db):
    """Lookahead limiter gain in dB, smooth by construction.

    The requirement is a running minimum over the lookahead window, the attack
    is a box average of that minimum across the same window (so the gain
    reaches the requirement exactly at the peak and ramps linearly in dB up to
    it), and the recovery is a one-pole release.
    """
    required = np.minimum(0.0, ceiling_db - peak_db)
    span = max(2, int(round(sr * LOOKAHEAD_MS / 1000.0)))
    worst = float(-required.min()) if required.size else 0.0
    if worst > 0:
        span = max(span, int(np.ceil(worst / MAX_GAIN_SLEW_DB)))
    span = min(span, max(2, required.shape[0]))
    look = _forward_running_min(required, span)
    # The ramp is padded with the first requirement, not with zero: a file that
    # starts loud must already be held down on its first sample, because there
    # is no earlier audio to ramp across.
    ramped = np.concatenate([np.full(span - 1, look[0]), look])
    cumulative = np.concatenate([[0.0], np.cumsum(ramped)])
    attack_db = (cumulative[span:] - cumulative[:-span]) / span
    return _release_curve(np.ascontiguousarray(attack_db[:peak_db.shape[0]]),
                          _coefficient(release_ms, sr))


def master(audio, sr, preset="balanced", target=-14):
    if preset not in PRESETS or not -20 <= target <= -9:
        raise ValueError("Invalid mastering settings")
    x = np.array(audio, dtype=np.float64, copy=True)
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
    x = high_shelf(x, sr, min(7500, sr * 0.35), p["air"])

    # Stereo-linked compressor. One detector across both channels, one gain
    # applied to both, so the stereo image is never pulled apart.
    hold = max(1, int(sr * 0.001))
    detector = ndimage.maximum_filter1d(np.max(np.abs(x), axis=1), hold)
    level_db = 20 * np.log10(np.maximum(detector, 1e-12))
    static_db = np.maximum(level_db - p["threshold"], 0) * (1 - 1 / p["ratio"])
    reduction = _follow(np.ascontiguousarray(static_db),
                        _coefficient(p["attack_ms"], sr), _coefficient(p["release_ms"], sr))
    x *= (10 ** (-reduction / 20))[:, None]
    compressor_reduction = float(np.max(reduction)) if reduction.size else 0.0

    # The limiter input is pre_gain * x, so its oversampled peak curve is this
    # one shifted by pre_gain in dB. Measuring it once keeps the loudness loop
    # from re-oversampling the whole file on every pass.
    peak_db = _oversampled_peak_db(x)
    ceiling_db = CEILING_DBTP - LIMITER_HEADROOM_DB
    after_compressor = loudness(x, sr)
    pre_db = 0.0 if after_compressor is None else min(target - after_compressor, MAX_PRE_GAIN_DB)

    y = x
    achieved = after_compressor
    limiter_reduction = 0.0
    passes = 0
    for attempt in range(MAX_LOUDNESS_PASSES):
        passes = attempt + 1
        gain_db = _limiter_gain_db(peak_db + pre_db, sr, p["limiter_release_ms"], ceiling_db)
        y = x * (10 ** ((pre_db + gain_db) / 20))[:, None]
        achieved = loudness(y, sr)
        limiter_reduction = float(-gain_db.min()) if gain_db.size else 0.0
        if achieved is None or achieved >= target - LOUDNESS_TOLERANCE_LU:
            break
        if limiter_reduction >= MAX_LIMITER_REDUCTION_DB or attempt == MAX_LOUDNESS_PASSES - 1:
            break
        step = min(target - achieved, MAX_PRE_GAIN_DB - pre_db)
        if step <= 0:
            break
        pre_db += step

    true_peak = _true_peak_dbtp(y)
    return y.astype(np.float32), {
        "input_lufs": before,
        "output_lufs": achieved,
        "target_lufs": target,
        "target_reached": bool(achieved is not None and achieved >= target - LOUDNESS_TOLERANCE_LU),
        "true_peak_dbtp": round(true_peak, 2),
        "max_gain_reduction_db": round(max(0.0, limiter_reduction), 2),
        "compressor_reduction_db": round(compressor_reduction, 2),
        "limiter_passes": passes,
        "preset": preset,
    }
