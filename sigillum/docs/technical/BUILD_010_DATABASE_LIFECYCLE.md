# Build 010 — migration-driven database lifecycle

**Date:** 2026-11-09  
**Base:** Build 009  
**Phase:** 02 — Repository, runtime and engineering foundation  
**Gate:** Phase 02 remains IN PROGRESS.

## Problem addressed

Before this build, development startup called `Base.metadata.create_all()` directly while production relied on Alembic. That made local startup convenient, but a local environment could appear healthy without exercising the checked-in migration chain. Readiness also checked only whether `SELECT 1` worked; it did not verify whether the database schema was at the repository's current migration head.

## Delivered

- Central database engine factory in `backend/sigillum/infrastructure/database/session.py`.
- SQLite paths create their configured parent directories; SQLite connections enable `PRAGMA foreign_keys=ON` and a bounded busy timeout.
- PostgreSQL shorthand URLs normalise to `postgresql+psycopg` (the project already pins `psycopg[binary]`); the PostgreSQL engine uses `pool_pre_ping`, bounded pool settings, connection timeout and application name.
- Database pool/timeout configuration is validated and exposed through `.env.example`.
- Development API startup now runs `alembic upgrade head`; the direct `Base.metadata.create_all()` application-startup shortcut is removed. Production remains migration-managed and does not auto-migrate.
- Alembic uses the same engine factory as the API, including correct SQLite parent-directory handling and PostgreSQL driver normalisation.
- Migration readiness reports current revision, expected revision, dialect and schema state. An unavailable or pending/out-of-date schema prevents readiness.
- The published initial migration remains unchanged. New revision `20261109_0002` installs `vector` on PostgreSQL; downgrade deliberately does not drop the cluster-level extension.
- `scripts/verify_database.py` checks the migration head, mapped tables and pgvector extension when PostgreSQL is used.
- CI defines a separate PostgreSQL 17 + pgvector service job which applies migrations to an empty database, verifies the schema/extension, then runs backend tests and the golden evaluation.
- Compose database and MinIO services are under an explicit `infra` profile so developers opt in to starting local backing services.

## Local validation in this authoring environment

- Backend suite: **72 passed**.
- Six database lifecycle tests cover: SQLite parent-folder creation, FK enforcement, PostgreSQL URL normalisation, unknown-dialect rejection, empty-database migration/idempotent re-upgrade, pending-schema detection and pool-config validation.
- `scripts/verify_database.py`: passed against SQLite, revision `20261109_0002`, all eight required tables present.
- Python compilation: passed.
- CI workflow YAML: parsed successfully with jobs `backend`, `backend-postgres` and `frontend`.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**.
- Live PostgreSQL/pgvector was not available in the authoring environment; psycopg was not installed in this runtime. The CI job is configured to provide that test, but its hosted run must be confirmed after push.
- Live MinIO/AWS was not available and remains unverified; Build 009's offline fake-client adapter tests remain the current S3 evidence.
- Ruff is not installed in the authoring environment; Ruff lint was not run.
- Frontend source was not changed, so frontend lint/typecheck/build was not rerun.

## Operational commands

```powershell
python -m alembic upgrade head
python scripts/verify_database.py
pytest
python -m compileall -q backend apps tests scripts
```

For local PostgreSQL + pgvector:

```powershell
docker compose -f infra/docker-compose.yml --profile infra up -d db
python -m alembic upgrade head
python scripts/verify_database.py
```

## Remaining Phase 02 work

The live PostgreSQL CI job must be observed passing. Live MinIO/S3, deployment secrets/TLS/storage policies, backup/restore, clean-checkout deployment, and durable asynchronous worker execution remain outstanding. Build 010 does not claim Phase 02 is complete or production-ready.
