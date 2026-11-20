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

The verification source/reference were four-second excerpts of the generic `source_s1.wav` and `s1p1.wav` example files in the upstream Seed-VC checkout, used only for local smoke testing. The three clearly named engine-check sessions remain in the app to demonstrate real outputs.
