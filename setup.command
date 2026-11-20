#!/bin/zsh
set -e
cd -- "${0:A:h}"
ROOT="$PWD"
export UV_CACHE_DIR="$ROOT/.runtime/cache"
export UV_PYTHON_INSTALL_DIR="$ROOT/.runtime/python"
export UV_PYTHON_BIN_DIR="$ROOT/.runtime/bin"
mkdir -p .runtime
if [[ ! -x .runtime/bootstrap/bin/uv ]]; then
  python3 -m venv .runtime/bootstrap
  .runtime/bootstrap/bin/python -m pip install --cache-dir .runtime/pip-cache uv==0.13.6
fi
UV="$ROOT/.runtime/bootstrap/bin/uv"
"$UV" python install 3.10.22
if [[ ! -x .venv/bin/python ]]; then
  "$UV" venv .venv --python 3.10.22
fi
"$UV" pip install --python .venv/bin/python -r requirements-lock.txt
if [[ ! -f vendor/seed-vc/inference.py ]]; then
  mkdir -p vendor
  git clone https://github.com/Plachtaa/seed-vc.git vendor/seed-vc
  git -C vendor/seed-vc checkout 51383efd921027683c89e5348211d93ff12ac2a8
fi
print '\nSetup complete. Open start.command to launch Forma.'
print 'Models download on first use; keep several GB of disk space available.'
