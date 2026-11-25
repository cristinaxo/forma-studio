# Component provenance

Forma's interface, local service, job management and mastering pipeline were written for this project. Third-party components remain separately identifiable.

| Component | Use | Upstream |
| --- | --- | --- |
| Demucs 4.0.1 | Local four-stem separation; htdemucs checkpoint | https://github.com/facebookresearch/demucs |
| Seed-VC, commit 51383efd921027683c89e5348211d93ff12ac2a8 | Local speech/singing conversion | https://github.com/Plachtaa/seed-vc |
| PyTorch / Torchaudio 2.4.0 | Local inference and audio operations | https://pytorch.org/ |
| Seed-VC model repository | Speech and singing checkpoints/configuration | https://huggingface.co/Plachta/Seed-VC |
| NVIDIA BigVGAN | Vocoder used by Seed-VC | https://huggingface.co/nvidia/bigvgan_v2_22khz_80band_256x and https://huggingface.co/nvidia/bigvgan_v2_44khz_128band_512x |
| CAMPPlus | Speaker embeddings used by Seed-VC | https://huggingface.co/funasr/campplus |
| RMVPE | Pitch extraction for singing conversion | https://huggingface.co/lj1995/VoiceConversionWebUI |
| Whisper | Content features inside the upstream Seed-VC pipeline | https://huggingface.co/openai/whisper-small |
| FastAPI / Uvicorn | Loopback HTTP service | https://fastapi.tiangolo.com/ |
| SciPy / NumPy / pyloudnorm | DSP and loudness measurement | https://scipy.org/ and https://github.com/csteinmetz1/pyloudnorm |
| imageio-ffmpeg | Packaged FFmpeg decoder | https://github.com/imageio/imageio-ffmpeg |

Demucs declares MIT licensing. Seed-VC declares GPL-3.0; its full license and source are retained in the vendor checkout. Model repositories and transitive packages have their own terms. This file records provenance rather than asserting a blanket license for all code, weights, data, or generated outputs. Dependency versions are captured in requirements-lock.txt.

The verification source/reference were four-second excerpts of the generic `source_s1.wav` and `s1p1.wav` example files in the upstream Seed-VC checkout, used only for local smoke testing. The three clearly named engine-check sessions remain in the app to demonstrate real outputs. Those example files are no longer in the checkout; see the removal note below.

## Changes to the vendored Seed-VC checkout

The checkout stays pinned to commit `51383efd921027683c89e5348211d93ff12ac2a8`. Its GPL-3.0 license remains in `vendor/seed-vc/LICENSE`.

### Removed upstream sample media

`vendor/seed-vc/examples/` (22 MB of source and reference clips) and `vendor/seed-vc/assets/real-time-demo.webm` (3.2 MB) were deleted. Nothing Forma runs reads them: the only upstream file Forma invokes is `inference.py`, and Forma always passes `--source` and `--target` explicitly, so the argparse defaults that point into `examples/` are never used. The remaining references are in the upstream Gradio demos (`app.py`, `app_vc.py`, `app_svc.py`, `app_vc_v2.py`), `eval.py` and `real-time-gui.py`, none of which Forma launches. Removing the media also removes third-party sample audio whose terms were never cleared for this project.

### Patches to `vendor/seed-vc/inference.py`

Two patches, both additive:

1. **Device override.** Before falling back to upstream's `cuda` / `mps` / `cpu` detection, the module honours `FORMA_VOICE_DEVICE` when it is set. Forma needs to pin the device per job; upstream had no way to do that except by reassigning the module global after import.
2. **Optional `--seed`.** A new `--seed` argument (default `None`, so upstream behaviour is unchanged when it is absent) seeds `random`, `numpy` and `torch` at the top of `main()` before any model loads. This is what makes a take reproducible.

### GPL boundary

Forma no longer does `import inference`. `process_audio.py` runs `vendor/seed-vc/inference.py` as a separate command-line program in its own process, passing the source, reference, output directory and inference settings as arguments. Forma's own code and the GPL-3.0 Seed-VC code are therefore separate programs communicating over a command line and the filesystem, not one combined work. This is a licensing boundary, not a performance change; a commercial release still needs its own review of the Seed-VC and model terms.
