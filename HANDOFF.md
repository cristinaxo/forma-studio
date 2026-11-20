# Recovered Forma source

Recovered from the October 27 Kits.ai project. This is an original local app inspired by an inspection; it is not proprietary Kits.ai backend source. README.md, THIRD_PARTY.md and VERIFICATION.md are original records. Their verification statements are historical, not fresh results.

## Fresh-machine setup
1. Extract the entire folder on an Apple Silicon Mac. Install Python 3 and Git if absent.
2. Open setup.command (or run `zsh setup.command`). It bootstraps uv 0.13.6, Python 3.10.22 and requirements-lock.txt. Network access is required. The retained Seed-VC source means its clone step normally skips.
3. Run `zsh start.command`, then open http://127.0.0.1:8765. Keep the terminal open. Stop with Control-C.
4. First model jobs download several GB of upstream weights. Models, package environments and user sessions are intentionally omitted. Use only audio and reference voices you have permission to process.
5. Run `.venv/bin/python -m pytest -q` for unit tests. Then use short permitted clips to check real mastering, stems and conversion. A clean-machine setup was not rerun for this handoff.

## Completeness and licenses
The original app source, static assets, tests, dependency lock and vendored Seed-VC source/license are included. No blanket license for the original app was found; no new license is invented. Upstream code/model terms still apply. GPL obligations and individual model rights require review before redistribution/commercial launch. Third-party sample assets remain under upstream terms; no blanket clearance is claimed.

Omitted: .venv, .runtime, .models, checkpoints, binary weights, caches, logs, data/session recordings and generated results. No real voices or private uploads are packaged. Example media already distributed with Seed-VC is retained as upstream material, not production content.
