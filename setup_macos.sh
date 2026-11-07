#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3.11+ from python.org or Homebrew, then run again.'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
if command -v brew >/dev/null 2>&1; then
  if ! brew list libomp >/dev/null 2>&1; then brew install libomp; fi
else
  echo 'If LightGBM reports a missing OpenMP library, install Homebrew from brew.sh and run: brew install libomp'
fi
if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python prepare.py
exec .venv/bin/python launch.py
