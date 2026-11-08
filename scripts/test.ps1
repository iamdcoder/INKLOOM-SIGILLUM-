$ErrorActionPreference = "Stop"
. .\.venv\Scripts\Activate.ps1
pytest
ruff check backend tests apps
