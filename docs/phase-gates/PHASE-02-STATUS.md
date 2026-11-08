# Phase 02 — Repository, runtime and engineering foundation

**Gate status: IN PROGRESS.** The backend foundation is executable and tested. The frontend source is present, but its production build has not been verified in this environment because the npm registry could not be resolved (`EAI_AGAIN`).

## Implemented and verified

- [x] Monorepo separation for web, API, worker, backend modules, fixtures, tests, documentation and infrastructure.
- [x] FastAPI `/api/v1` application with request IDs, CORS allowlist, typed request models and structured error responses.
- [x] Liveness and readiness endpoints; readiness checks the database, storage directory and Brand Knowledge Pack fingerprint and returns HTTP 503 on failure.
- [x] SQLAlchemy models and an initial Alembic migration for users, submissions, content versions, review runs, findings, patches, decisions and audit events.
- [x] SQLite development runtime and private local filesystem storage; original content uses opaque generated keys and SHA-256 hashes.
- [x] Review records persist the full Brand Knowledge Pack snapshot, its SHA-256 fingerprint and the deterministic analysis configuration version.
- [x] API exposes the immutable content-version history and each review's governing pack fingerprint, finding count and decisions.
- [x] Next.js App Router source for login, overview, submissions, upload, review workbench, Brand Control Center and audit history.
- [x] Python unit/integration suite: 27 passing tests in the current local run.
- [x] Synthetic golden evaluation: 11 automated PASS, 1 explicit MANUAL_REVIEW_REQUIRED, 0 FAIL, 12 total.

## In progress / not yet verified

- [ ] Clean-machine frontend install, lockfile generation, `npm run lint`, `npm run typecheck` and `npm run build`.
- [ ] Full PostgreSQL/pgvector and MinIO adapter wiring. Compose currently provisions local infrastructure only; the MVP runtime uses SQLite and filesystem storage.
- [ ] Durable worker queue, LangGraph checkpoints, leases, idempotency, SSE progress and restart recovery. The present review operation is synchronous in the API process.
- [ ] Production tenant membership and PostgreSQL RLS. Current demo authorization is a single synthetic workspace with creator ownership and role-gated reviewer actions.
- [ ] CI pipeline and a clean-checkout smoke run on the participant's machine.

## Reproducibility evidence

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

Do not close this phase until those frontend commands pass on a clean machine and the migration starts from an empty database.
