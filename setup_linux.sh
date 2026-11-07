#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3.11+ with pip and venv, then run this script again.'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
if ! .venv/bin/python -c 'import lightgbm' >/dev/null 2>&1; then
  echo 'LightGBM needs the OpenMP runtime. Install libgomp (Debian/Ubuntu: sudo apt install libgomp1; Fedora: sudo dnf install libgomp), then rerun.'
  exit 1
fi
.venv/bin/python prepare.py
exec .venv/bin/python launch.py
