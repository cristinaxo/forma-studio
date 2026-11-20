# Forma — local audio studio

An original, self-hosted phase-one audio creation app. Runs on this Apple Silicon Mac with no paid inference API, subscription, usage credits, or cloud audio uploads.

## Open the studio

Double-click **start.command** in this folder, then use **http://127.0.0.1:8765**. Keep its Terminal window open while processing. Control-C stops the server. Projects and audio remain saved when the server stops. On the initial computer, the environment and tested models are already installed.

If the folder is moved or copied to another Mac, run **setup.command** to install the isolated Python environment and model software. If an existing virtual environment was copied, remove only `.venv` and rerun setup. Initial installation needs Python 3 and Git and internet access; it does not install a global Python package or configure a cloud account.

## Phase 1

- Upload common audio formats or record from the microphone with browser permission.
- Preview the actual input waveform and listen before processing.
- Voice conversion using a clean reference voice, powered by Seed-VC. Speech and singing modes, diffusion detail, and singing pitch shift.
- Four-stem separation using Demucs: vocals, drums, bass, and other instruments.
- Local mastering: high-pass filtering, tonal EQ, stereo-linked compression, loudness targeting, lookahead limiting and a 4x oversampled peak check. This is signal processing, not a generative AI model. Reports achieved LUFS and estimated true peak.
- Persistent sessions, one-at-a-time processing queue, cancellation, source/result comparison, individual lossless WAV downloads, project search and deletion.

Limits: 50 MB per input; 180 seconds for mastering and stems; 30 seconds for voice conversion; reference voice 3–30 seconds. These bounds keep the initial CPU implementation manageable. A maximum of three queued/running jobs is accepted. Processing stops after one hour if an engine stalls. Voice conversion quality depends on source, reference, and inference settings. Longer or finer runs can be slow.

## Where the files live

- `data/`: session metadata, source audio, references, logs, and output WAV files. Never uploaded by this app.
- `.models/`: Demucs and package caches.
- `vendor/seed-vc/checkpoints/`: cached Seed-VC, vocoder, speaker-embedding and content-encoder weights.
- `.venv/`: isolated Python packages.

Model weights download from upstream repositories on first use. Subsequent loads can still check model metadata online; audio is not sent to those repositories. If fully offline operation is needed, cache the desired models first, then set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` when launching. Microphone access was implemented but was not exercised against the user's microphone during testing.

The first installation used a workspace-local Python 3.10 runtime outside this folder. `setup.command` can create a replacement under `.runtime/` if the original runtime is removed. No launch agent or system startup service is installed.

## Run manually

```sh
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8765
```

This version binds only to loopback and is designed for one local user. It rejects foreign Host and Origin headers. It is not an internet-facing, authenticated multi-user service. Do not change the bind address without adding an appropriate access-control layer.

The conservative default inference device is CPU. Seed-VC has upstream Apple Silicon support, but this app's tested baseline is CPU. An advanced deployment can set `FORMA_VOICE_DEVICE=mps` after validating that device separately. Future GPU acceleration does not require changing the interface.

## Tests

```sh
.venv/bin/python -m pytest -q
```

The test suite verifies mastering output properties, silence and settings validation, origin/host restrictions, invalid audio rejection, reference requirements and duration limits. Real model smoke checks are separate from unit tests because they download weights and are slower.

## Next phases

Phase 2: vocal generation, voice designer, harmony generation. Phase 3: expanded model library, editing and batch workflows. These features are planned, not implemented in this version.

## Third-party components

Demucs: https://github.com/facebookresearch/demucs (MIT).
Seed-VC: https://github.com/Plachtaa/seed-vc (GPL-3.0), pinned to `51383efd921027683c89e5348211d93ff12ac2a8`; its original license is retained in `vendor/seed-vc/LICENSE`. It runs as a separate local inference component. Other dependencies and model weights retain their upstream licenses. See THIRD_PARTY.md. A commercial release needs a separate review of the selected model and dependency terms.
