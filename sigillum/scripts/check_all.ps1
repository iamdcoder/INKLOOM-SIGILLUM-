$ErrorActionPreference = "Stop"
. .\.venv\Scripts\Activate.ps1

Write-Host "[1/5] Python compile check" -ForegroundColor Cyan
python -m compileall -q backend apps tests scripts

Write-Host "[2/5] Backend tests" -ForegroundColor Cyan
pytest

Write-Host "[3/5] Synthetic golden evaluation" -ForegroundColor Cyan
python scripts/evaluate_golden_cases.py

Write-Host "[4/5] Python lint" -ForegroundColor Cyan
ruff check backend apps tests scripts

Write-Host "[5/5] Frontend lint, typecheck and production build" -ForegroundColor Cyan
Push-Location apps\web
try {
    if (!(Test-Path node_modules)) { npm install }
    npm run lint
    npm run typecheck
    npm run build
}
finally {
    Pop-Location
}

Write-Host "All available checks completed." -ForegroundColor Green
