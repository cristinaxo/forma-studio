import numpy as np
import pytest
from scipy.signal import resample_poly
import audio_engine
from audio_engine import master

def test_master_preserves_audio_and_controls_true_peak():
    sr = 44100
    t = np.arange(sr * 2) / sr
    x = np.stack([.06 * np.sin(2*np.pi*220*t), .04 * np.sin(2*np.pi*330*t)], axis=1)
    original = x.copy()
    y, stats = master(x, sr, "balanced", -14)
    assert y.shape == x.shape
    assert np.isfinite(y).all()
    assert np.array_equal(x, original)
    assert stats["output_lufs"] > stats["input_lufs"]
    assert np.max(np.abs(resample_poly(y, 4, 1, axis=0))) <= 10**(-.99/20)
    assert np.max(np.abs(y-x)) > .01

def test_silent_audio_rejected():
    with pytest.raises(ValueError, match="silent"):
        master(np.zeros((44100,2)),44100)

def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        master(np.zeros((44100,2)),44100,"made-up")

def test_loud_transients_remain_finite_and_limited():
    sr = 44100
    x = np.random.default_rng(7).normal(0,.05,(sr,2))
    x[5000:5010] = 1
    y,stats = master(x,sr,"punch",-9)
    assert np.isfinite(y).all()
    assert stats["true_peak_dbtp"] <= -.99

def test_limiter_gain_curve_never_steps():
    """The gain curve must ramp, not jump: at most 0.1 dB between samples."""
    sr = 44100
    rng = np.random.default_rng(11)
    x = rng.normal(0, .2, (sr * 2, 2))
    x[sr // 2:sr // 2 + 4] = 1.0          # a near-instant full-scale transient
    x[sr: sr + 400] *= 3.0                # and a loud burst
    peak_db = audio_engine._oversampled_peak_db(x)
    for release in (50.0, 150.0):
        gain_db = audio_engine._limiter_gain_db(peak_db, sr, release, audio_engine.CEILING_DBTP)
        assert gain_db.max() <= 1e-9, "the limiter must never add gain"
        assert np.abs(np.diff(gain_db)).max() <= 0.1

def test_true_peak_stays_under_the_ceiling():
    sr = 44100
    rng = np.random.default_rng(5)
    t = np.arange(sr * 3) / sr
    x = np.stack([.3 * np.sin(2 * np.pi * 997 * t) + rng.normal(0, .1, t.shape),
                  .3 * np.sin(2 * np.pi * 1109 * t) + rng.normal(0, .1, t.shape)], axis=1)
    for preset, target in (("punch", -9), ("balanced", -14), ("warm", -20)):
        y, stats = master(x, sr, preset, target)
        measured = 20 * np.log10(max(float(np.max(np.abs(resample_poly(y, 4, 1, axis=0)))), 1e-12))
        assert measured <= audio_engine.CEILING_DBTP, (preset, target, measured)
        assert stats["true_peak_dbtp"] <= audio_engine.CEILING_DBTP

def dense_mix(sr=44100, seconds=6):
    """A busy broadband mix with real transients, not a single tone."""
    rng = np.random.default_rng(23)
    t = np.arange(sr * seconds) / sr
    tone = sum(np.sin(2 * np.pi * f * t + i) for i, f in enumerate((55, 110, 165, 220, 440, 880, 1760))) / 7
    body = .45 * tone + .22 * rng.normal(0, 1, t.shape)
    hits = np.zeros_like(t)
    hits[::sr // 4] = 1
    decay = np.exp(-np.arange(int(sr * .12)) / (sr * .02))
    hits = np.convolve(hits, decay)[:t.size]
    mix = body + .5 * hits
    wide = np.stack([mix, np.roll(mix, 13) * .97], axis=1)
    return wide / np.max(np.abs(wide)) * .7

def test_dense_mix_reaches_minus_nine_or_reports_it_cannot():
    sr = 44100
    y, stats = master(dense_mix(sr), sr, "punch", -9)
    assert np.isfinite(y).all()
    assert stats["output_lufs"] is not None
    if stats["target_reached"]:
        assert abs(stats["output_lufs"] - (-9)) <= 0.5, stats
    else:
        assert stats["output_lufs"] < -9 + 0.5, stats
    assert stats["true_peak_dbtp"] <= audio_engine.CEILING_DBTP
    assert stats["max_gain_reduction_db"] >= 0

def test_loudness_loop_retries_then_reports_an_unreachable_target():
    """High crest factor material: the loop must iterate, then stop honestly."""
    sr = 44100
    rng = np.random.default_rng(4)
    n = sr * 6
    x = np.zeros((n, 2))
    for start in range(0, n - sr // 4, int(sr * .4)):
        length = int(sr * .06)
        x[start:start + length] += rng.normal(0, .45, (length, 2)) * np.hanning(length)[:, None]
    x += rng.normal(0, .0015, (n, 2))
    y, stats = master(x, sr, "punch", -16)
    assert 1 < stats["limiter_passes"] <= audio_engine.MAX_LOUDNESS_PASSES, stats
    assert stats["target_reached"] is False, stats
    assert stats["output_lufs"] < -16, stats
    assert stats["true_peak_dbtp"] <= audio_engine.CEILING_DBTP, stats
    assert np.isfinite(y).all()
