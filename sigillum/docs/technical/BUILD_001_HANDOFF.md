# Build 001 handoff — Inkloom Sigillum

**Snapshot date:** 2026-11-08  
**Build status:** backend MVP verified; frontend source supplied but production build unverified.

## What this snapshot contains

- FastAPI API with local demo authentication, role-gated review decisions, structured errors and readiness/liveness checks.
- SQLAlchemy persistence and initial Alembic migration.
- Secure local file intake, supported-format validation, PDF/DOCX/TXT extraction and local PNG/JPG OCR.
- Immutable source versions and content hashes.
- Deterministic, deliberately narrow claim/terminology/tone checks against the synthetic ORBITA Brand Knowledge Pack.
- Finding ledger, manual-review gates, version-bound decisions and audit events.
- Hash-bound text patching, revised content versions and a review-history endpoint.
- Next.js source for login, overview, submission, review workbench, brand snapshot and audit history.
- 27 backend unit/integration tests and 12 synthetic golden cases.

## Verification captured for this snapshot

| Check | Captured result |
|---|---|
| `pytest -q` | 27 passed |
| `python scripts/evaluate_golden_cases.py` | 11 automated PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL |
| `python -m compileall -q backend apps tests scripts` | Passed |
| Initial Alembic migration against SQLite | Passed |
| TypeScript/TSX syntax transpilation | 14 files, 0 syntax diagnostics; not a full typecheck |
| API health, demo login, TXT submission, `CONTRADICTED` result and history endpoint | Passed in local HTTP smoke test |
| `npm install` | Not completed in authoring environment (`EAI_AGAIN registry.npmjs.org`) |
| Frontend lint, full typecheck and production build | Not verified; run on participant machine |

The golden set is a narrow, synthetic deterministic regression suite. Its result is not a general accuracy estimate, user study, legal certification or accessibility certification.

## Windows setup

### Terminal 1 — API

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data | Out-Null
python -m alembic upgrade head
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate again.

### Terminal 2 — Web

```powershell
cd apps\web
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. API docs are at `http://127.0.0.1:8000/docs` and readiness is at `http://127.0.0.1:8000/health/ready`.

Demo accounts (local development only):

- `creator@orbita.demo`
- `reviewer@orbita.demo`
- `owner@orbita.demo`
- `admin@orbita.demo`

The default local password is `ChangeMe-Local-Only`. Never use it with public deployment or real confidential material.

## Before calling this release-ready

1. On the participant machine, complete `npm install` and retain the generated `apps/web/package-lock.json`.
2. Run `npm run lint`, `npm run typecheck` and `npm run build` from `apps/web`; fix all failures.
3. Run `pytest`, the golden evaluator and migration from a clean checkout.
4. Install Tesseract locally and confirm PNG/JPG OCR on the participant machine.
5. Walk through the creator → finding/evidence → TXT patch → new immutable version → reviewer decision → audit flow.
6. Review every disclosed pre-window artefact, dependency, synthetic fixture and AI-assisted component against organiser requirements. Do not fabricate build-window timestamps or contribution history.

## Scope limits that must be disclosed

This is a single-workspace local MVP. SQLite and local file storage are active; Postgres/pgvector and MinIO are compose scaffolds only. Reviews run synchronously in the API; durable worker jobs, LangGraph checkpoints, SSE replay and restart recovery are not active. Hybrid vector retrieval is not active. The deterministic checker supports a narrow set of configured claim patterns, not general semantic or legal verification. Tesseract OCR is used for PNG/JPG; scanned-PDF and embedded-image OCR are not implemented. Logo identity, palette and standards-grade contrast are manual-review items. TXT patches are supported; flattened creative files must be edited in their native application and uploaded as a new version. No hosted LLM or external AI API is called by this build.
