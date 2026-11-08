# Judge demonstration runbook

## 1. Environment

- Python 3.11 or newer (3.13 recommended).
- Node.js 20 or newer (22 recommended) and npm.
- Tesseract OCR installed and available on PATH for local image OCR. If installed elsewhere, set `TESSERACT_CMD` in `.env` to the executable path.
- No hosted AI key is required. No external LLM provider is called by this build.

## 2. Start API (Windows PowerShell)

From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python -m alembic upgrade head
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

The API creates the demo SQLite schema and seeded demo identities on startup in development mode. Verify `http://127.0.0.1:8000/health/ready`.

## 3. Start web application

In a second terminal:

```powershell
cd apps\web
if (!(Test-Path .env.local)) { Copy-Item .env.local.example .env.local }
npm install
npm run dev
```

Open `http://localhost:3000`. Set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1` in `apps/web/.env.local` if it differs.

## 4. Demo accounts

All local-only seeded users use the value of `SIGILLUM_DEMO_PASSWORD` in `.env` (default: `ChangeMe-Local-Only`). Change it for any shared or deployed environment.

| Role | Email |
|---|---|
| Creator | `creator@orbita.demo` |
| Reviewer | `reviewer@orbita.demo` |
| Brand owner | `owner@orbita.demo` |
| Administrator | `admin@orbita.demo` |

Do not use these demo credentials for real content or a public production deployment.

## 5. Primary end-to-end demonstration

1. Sign in as `creator@orbita.demo`.
2. Open **New review**.
3. Upload `fixtures/documents/claim_40_percent.txt` (or select the 40% PDF/DOCX fixture). Choose channel `direct_web`, offer `OFFER-ORBITA-OCT-NOV-2026`, locale `en-IN`, geography `IN`, audience `consumer`, and a publication timestamp inside the fact's validity period.
4. Expand the `CONTRADICTED` claim finding. Show the exact `up to 40%` content span, the approved 28% source reference, scope and validity dates.
5. For TXT, apply the proposed `up to 28%` patch. The system must create version 2 with a different SHA-256 and a new review. For PDF/DOCX/image, edit the source in its native editor and upload it through **Submit a revised source**.
6. Sign out and sign in as `reviewer@orbita.demo`.
7. Open the submission. Resolve any remaining manual-review findings with a reason after inspecting the original asset.
8. Approve only the exact re-verified version. Show the decision hash and audit record.
9. Open the Audit view and show the submission, patch/revision and decision events.

## 6. Edge cases to show

- Expired offer: `fixtures/documents/expired_20_percent.txt` with the expired offer ID and an intended publication time after September 30, 2026 → `STALE`.
- Future offer: `fixtures/documents/future_25_percent.txt` with the December offer but a November publication time → `UNVERIFIABLE / FACT_NOT_YET_VALID`.
- Conflicting sources: `fixtures/documents/conflicting_29_percent.txt`, social channel and `OFFER-ORBITA-CONFLICT-TEST` → `CONFLICTING`.
- Wrong scope: submit a direct-web fact claim under social channel → `UNVERIFIABLE`.
- Low-confidence image: `fixtures/images/social_low_confidence_ocr.png` → extraction confidence below 0.75, manual review.
- Prompt injection text: upload an instruction-like phrase → untrusted-content finding; it is never executed.

## 7. Verification commands

```powershell
pytest
python scripts/evaluate_golden_cases.py
python -m compileall -q backend apps tests scripts
```

The synthetic golden evaluator currently targets 12 labelled cases: 11 automated PASS, 1 explicit visual MANUAL_REVIEW_REQUIRED and 0 FAIL at the current recorded run. It is a deterministic regression set, not an accuracy estimate.

## 8. Fallback demonstration

If the frontend cannot be installed in the judging environment, use FastAPI docs at `http://127.0.0.1:8000/docs` and the same seeded demo identities to exercise the API. Do not claim the frontend build passed unless `npm run build` has been run successfully in the target environment.
