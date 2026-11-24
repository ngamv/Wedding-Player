#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if ! command -v python3.12 >/dev/null 2>&1; then
  printf '%s\n' "Python 3.12 est requis. Installez-le depuis python.org ou avec brew install python@3.12."
  exit 1
fi

python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
exec .venv/bin/python lancer_orion.py "$@"
