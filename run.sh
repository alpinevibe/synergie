#!/usr/bin/env bash
# Synergie — lancement local.
#   ./run.sh            → http://127.0.0.1:8077
#   ./run.sh --hote 0.0.0.0 --port 8078
set -euo pipefail
racine="$(cd "$(dirname "$0")" && pwd)"
python="${SYNERGIE_PYTHON:-/home/ubuntu/synergie-venv/bin/python}"
[ -x "$python" ] || python="$(command -v python3)"
exec "$python" "$racine/serveur.py" "$@"
