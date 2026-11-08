# Phase 02 — Repository, runtime and engineering foundation

**Gate status: IN PROGRESS.** The backend foundation is executable and tested. The participant has verified the frontend lint, TypeScript and production build gates on Windows; remaining work is infrastructure integration, CI and clean-checkout operations evidence.

## Implemented and verified

- [x] Monorepo separation for web, API, worker, backend modules, fixtures, tests, documentation and infrastructure.
- [x] FastAPI `/api/v1` application with request IDs, CORS allowlist, typed request models and structured error responses.
- [x] Liveness and readiness endpoints; readiness checks the database, storage directory and Brand Knowledge Pack fingerprint and returns HTTP 503 on failure.
- [x] SQLAlchemy models and an initial Alembic migration for users, submissions, content versions, review runs, findings, patches, decisions and audit events.
- [x] SQLite development runtime and private local filesystem storage; original content uses opaque generated keys and SHA-256 hashes.
- [x] Review records persist the full Brand Knowledge Pack snapshot, its SHA-256 fingerprint and the deterministic analysis configuration version.
- [x] API exposes the immutable content-version history and each review's governing pack fingerprint, finding count and decisions.
- [x] Participant Windows frontend install, lint, typecheck and production build passed on 2026-11-08; retain the generated `apps/web/package-lock.json`.
- [x] Live HTTP vertical-slice smoke executed against a clean local API/database: 8 checks passed.
- [x] Next.js App Router source for login, overview, submissions, upload, review workbench, Brand Control Center and audit history.
- [x] Review Workbench finding search, severity/category/verdict/status filters, risk-first sorting, exact text-span navigation, and richer available evidence/region provenance display (Build 005; local lint/typecheck/build re-verification pending).
- [x] Python unit/integration suite: 27 passing tests in the current local run.
- [x] Synthetic golden evaluation: 11 automated PASS, 1 explicit MANUAL_REVIEW_REQUIRED, 0 FAIL, 12 total.

## In progress / not yet verified

- [ ] Full PostgreSQL/pgvector and MinIO adapter wiring. Compose currently provisions local infrastructure only; the MVP runtime uses SQLite and filesystem storage.
- [ ] Durable worker queue, LangGraph checkpoints, leases, idempotency, SSE progress and restart recovery. The present review operation is synchronous in the API process.
- [ ] Production tenant membership and PostgreSQL RLS. Current demo authorization is a single synthetic workspace with creator ownership and role-gated reviewer actions.
- [ ] CI pipeline and a clean-checkout smoke run on the participant's machine.

## Reproducibility evidence

The participant's Windows terminal confirmed the frontend lint, TypeScript check and production build successfully. Separately, `python scripts/smoke_vertical_slice.py` was executed against a clean local API/database and passed all 8 workflow checks. The script creates a synthetic submission and ends by approving its corrected version; it does not modify existing submissions.

From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
python -m alembic upgrade head
pytest
python scripts/evaluate_golden_cases.py
python scripts/smoke_vertical_slice.py  # API must be running on 127.0.0.1:8000
python -m compileall -q backend apps tests scripts
```

In a second terminal:

```powershell
cd apps\web
Copy-Item .env.local.example .env.local
npm install
npm run lint
npm run typecheck
npm run build
```

The frontend commands have passed on the participant's Windows machine. The full Phase 02 gate remains open until a clean-checkout setup is repeated and the selected Postgres/MinIO infrastructure is genuinely wired and tested (or formally deferred for the event MVP), CI passes, and operational deployment checks are complete.
