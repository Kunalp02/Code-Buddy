#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if python3 -m venv .venv 2>/dev/null; then
  source .venv/bin/activate
  pip install -q -r server/requirements.txt
else
  pip3 install -q -r server/requirements.txt
  export PATH="$HOME/.local/bin:$PATH"
fi

if [ ! -d "web/node_modules" ]; then
  cd web && npm install && cd "$ROOT"
fi

trap 'kill 0' EXIT

source .venv/bin/activate
PYTHONPATH="$ROOT" uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload &
cd web && npm run dev
