import numpy as np
import pytest
from scipy.signal import resample_poly
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
