# Verification

Verified on the attached Apple Silicon Mac using Python 3.10.22 and CPU inference.

- 9 automated tests passed: loudness changes, output shape, non-mutated source arrays, finite samples, oversampled peak ceiling, silence/settings validation, origin/host restrictions, invalid audio cleanup, reference requirements and voice duration limit.
- Demucs processed a 4-second speech fixture into four valid 44.1 kHz WAV files. The vocal stem dominated, as expected for that input. This verifies execution and exports, not separation quality on a full music mix.
- Seed-VC speech conversion produced a non-silent, approximately 4-second 22.05 kHz WAV from source and reference fixtures.
- Seed-VC singing mode also produced a non-silent, approximately 4-second 44.1 kHz WAV. The smoke input was speech, so this does not establish musical conversion quality.
- Through the app's HTTP endpoints, real stem and voice jobs completed; every output download returned a valid RIFF/WAV file.
- Through the browser UI, a WAV was uploaded, its waveform was displayed, and a mastering job completed. Input loudness was −18.68 LUFS; output was −14.00 LUFS, with an estimated true peak of −2.92 dBTP. The result panel exposed both original and output players and downloads.
- The browser console contained no warnings/errors at the checked state. Project navigation and the narrower layout were inspected. The viewport tool reported 780 CSS pixels for a requested 390-pixel override, so a true phone-width viewport was not established by that check.
- Microphone recording is implemented with MediaRecorder and requires browser permission. It was not exercised against the user's microphone.

Not established: full-length music quality, throughput under multiple concurrent users, all possible codecs, GPU/MPS correctness, commercial model suitability, or internet-facing deployment. CPU inference is the verified baseline. Limits are deliberately conservative for this first version.

## 2026-11-24 — limiter, dynamics, GPL boundary and voice consistency

Measured on the same Apple Silicon Mac, Python 3.10.22, CPU inference, on the `cleanup-limiter-voice` branch. Test material was the first 179.5 seconds of `mix.wav` and the first 29.5 seconds of `acapella.wav` and `reference.wav`, trimmed because the full files exceed the app's own 180-second and 30-second limits. Baseline and after runs used the identical trims.

- 18 automated tests pass, up from 9. The new ones cover: the limiter gain curve never moving more than 0.1 dB between adjacent samples (checked at both the 50 ms and 150 ms preset releases); the 4x oversampled true peak staying at or under -1.0 dBTP across three presets and targets; a dense synthetic mix at -9 landing within 0.5 LU or reporting `target_reached: false`; the loudness loop actually iterating and then stopping honestly on high crest factor material; a `testserver` Host returning 403 against the shipped allowlist; a non-numeric Content-Length returning 400; a fourth concurrent job returning 429; a reserved queue slot being counted before the upload is decoded; and the extended 40/50 step options being accepted.

### Mastering, `mix.wav` at preset punch, through the HTTP API

| | before | after |
| --- | --- | --- |
| target -14 | 10.9 s, -14.00 LUFS, -1.28 dBTP | 6.8 s, -14.02 LUFS, -1.05 dBTP, 2.08 dB max gain reduction, target reached |
| target -9 | 10.6 s, -11.66 LUFS, -1.00 dBTP | 6.1 s, -10.21 LUFS, -1.05 dBTP, 7.08 dB max gain reduction, target **not** reached |

The -9 target is still not reached, and that is now reported rather than hidden. Reaching -9 on this material needs 7.08 dB of limiting, above the 6 dB cap, so the loudness loop stops and the result panel says the target was not reachable without over-limiting. The engine call itself measures 3.8 to 4.0 seconds for the 179.5 second file; the 6.1 and 6.8 second figures are the whole subprocess, including reading and writing 45 MB of 24-bit WAV.

### Stem separation

84.9 s before, 84.5 s after. All four output files are bit-identical between the two runs, which confirms the restructuring of `process_audio.py` left the Demucs path untouched.

### Voice conversion, singing mode, 30 steps

| | seconds |
| --- | --- |
| before, first run including multi-GB weight downloads | 1127.2 |
| before, same code with warm caches | 993 |
| after, through the HTTP API | 1020.1 |
| after, direct, two further runs | 961 and 1047 |

Conversion time is unchanged. The spread between identical repeat runs (961 to 1047 seconds) is wider than any difference between before and after, so no speed claim is made in either direction. The original 1127.2 second figure is not comparable, because it included the first download of the model weights.

Outputs before and after are both 29.536 s at 44.1 kHz and non-silent. The after output has lower RMS (0.0765 against 0.1144) because both inputs are now loudness-normalised to -20 LUFS before inference; on this pair the source measured -13.56 LUFS and the reference -17.0 LUFS, a 3.4 LU difference that previously fed straight into the conversion.

### Reproducibility

Two conversions with identical settings and seed 1234 on cpu produced **bit-identical audio**: 1,302,528 frames each, zero differing samples, correlation 1.000000, maximum absolute difference 0.0. The two files are not identical on disk, but only because the WAV `PEAK` chunk embeds a creation timestamp; exactly two bytes differ, at offset 0x38, and they are metadata rather than audio. Seed, steps, mode, pitch, device and the resolved Seed-VC checkpoint name are written into the session record, so a take can be reproduced from what the app stored.

### mps

Not adopted. `FORMA_VOICE_DEVICE=mps` fails on both attempts after about 25 to 30 seconds, at `inference.py` in the pitch path: `F0_ori = torch.from_numpy(F0_ori).to(device)` raises `Cannot convert a MPS Tensor to float64 dtype as the MPS framework doesn't support float64`. The RMVPE pitch extractor returns float64, which the MPS backend cannot hold. The failure happens before inference begins, so there is no partial, silent or degraded output to compare, and no CPU fallback was triggered: the job exits non-zero. `PYTORCH_ENABLE_MPS_FALLBACK=1` is already set and does not help, because the problem is a rejected dtype rather than a missing operator. cpu stays the default and the override remains available.

Not established by this round: speech-mode conversion on mps, musical quality of any conversion, full-length material beyond the app's 180-second limit, behaviour under concurrent users, or any change to the Demucs or model licensing position.
