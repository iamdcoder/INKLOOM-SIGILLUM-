$ErrorActionPreference = "Stop"
if (!(Test-Path .venv)) { py -3.13 -m venv .venv }
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force data | Out-Null
python -m alembic upgrade head
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
