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
