#!/usr/bin/env bash
set -euo pipefail
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
[ -f .env ] || cp .env.example .env
mkdir -p data
python -m alembic upgrade head
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
