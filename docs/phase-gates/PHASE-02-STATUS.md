# Phase 02 — Repository, runtime and engineering foundation

**Gate status: IN PROGRESS.** Build 010 closes the local migration lifecycle gap and adds a PostgreSQL/pgvector service-backed CI path. The full Phase 02 exit gate remains open until the hosted PostgreSQL job is observed passing, a live MinIO/S3 path is exercised, and the remaining operational requirements are proven.

## Implemented and verified

- [x] Monorepo separation for web, API, worker scaffold, backend modules, fixtures, tests, documentation and infrastructure.
- [x] FastAPI `/api/v1` application with request IDs, CORS allowlist, typed request models and structured error responses.
- [x] Liveness and readiness endpoints; readiness separately checks database connectivity, Alembic migration head, configured object storage and Brand Knowledge Pack fingerprint.
- [x] Development startup applies the checked-in Alembic migration chain; ad hoc `Base.metadata.create_all()` startup schema creation has been removed.
- [x] SQLite engine creates configured parent directories and enables foreign-key enforcement and a bounded busy timeout.
- [x] PostgreSQL shorthand URLs are normalised to the pinned psycopg 3 driver; PostgreSQL engine uses connection pre-ping, bounded pool settings and connection timeouts.
- [x] Initial schema migration is preserved; a forward-only migration installs pgvector on PostgreSQL without modifying the published initial revision.
- [x] `scripts/verify_database.py` reports dialect, current/expected migration revision, missing mapped tables and pgvector availability.
- [x] Object-storage port with private atomic local writes and opt-in boto3 S3-compatible adapter; authenticated downloads recompute SHA-256 and reject corrupted bytes (Build 009).
- [x] Storage-provider failures return a distinct non-approved `STORAGE_UNAVAILABLE` response rather than being misreported as parser failures (Build 009).
- [x] Review records persist the full Brand Knowledge Pack snapshot, its SHA-256 fingerprint and deterministic analysis configuration version.
- [x] API exposes immutable content-version history and each review's governing pack fingerprint, finding count and decisions.
- [x] Next.js App Router source for login, overview, submissions/upload, review workbench, Brand Control Center and audit history.
- [x] CI workflow now has a dedicated PostgreSQL 17 + pgvector service job that installs the project dependencies, applies Alembic migrations from an empty database, verifies schema/extension, and runs backend tests and golden evaluation.
- [x] SQLite/local-mode backend suite: **72 passing tests** in the Build 010 authoring environment.
- [x] Fresh temporary SQLite database migration test: upgrade from empty, schema presence, repeat upgrade at head and migration readiness checks.
- [x] Database verification script passed against the local SQLite database; current revision **20261109_0002**, all eight required tables present.
- [x] Python compilation passed.
- [x] Synthetic golden evaluation: **11 automated PASS, 1 explicit MANUAL_REVIEW_REQUIRED, 0 FAIL**, 12 total.
- [x] Participant Windows frontend install, lint, typecheck and production build passed on 2026-11-08; frontend source was not changed in Build 010.

## In progress / not yet verified

- [ ] Hosted PostgreSQL 17 + pgvector CI job has not yet been observed running; local authoring environment has no PostgreSQL service and does not have the psycopg package installed.
- [ ] Live MinIO/AWS S3 endpoint verification, bucket policies, provider-side encryption, backups, retention and deletion lifecycle.
- [ ] Durable worker queue, LangGraph checkpoints, leases, idempotency, SSE progress and restart recovery. Review execution remains synchronous in the API process.
- [ ] Production tenant membership and PostgreSQL RLS. Current demo authorization remains a single synthetic workspace with creator ownership and role-gated reviewer actions.
- [ ] Full clean-checkout deployment and frontend verification after the final source changes.

## Reproducibility

From the repository root on Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
python -m alembic upgrade head
python scripts/verify_database.py
pytest
python scripts/evaluate_golden_cases.py
python -m compileall -q backend apps tests scripts
```

To exercise PostgreSQL + pgvector locally, set `DATABASE_URL` to a `postgresql+psycopg://` URL matching `POSTGRES_PASSWORD` in `.env`, then run:

```powershell
docker compose -f infra/docker-compose.yml --profile infra up -d db
python -m alembic upgrade head
python scripts/verify_database.py
```

The hosted CI PostgreSQL job performs the same migration and schema checks against a fresh PostgreSQL 17 + pgvector service. Its success status must be confirmed in GitHub Actions after the Build 010 commit/push.
