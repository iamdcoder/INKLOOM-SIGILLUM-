# Inkloom Sigillum — Build 010 Patch

**Base:** Build 009  
**Increment:** Migration-Driven Database Lifecycle and PostgreSQL CI  
**Date:** 2026-11-09

## Apply

This ZIP is a complete source snapshot based on Build 009. It already includes the Build 009 storage implementation and the previous project files. Back up your current repository folder, then extract the ZIP over the repository root while preserving all paths.

The archive intentionally excludes `.env`, local databases and uploaded content, `.venv`, `node_modules`, `.next`, Python caches and Git internals. Keep your existing `.env`, `data/`, `.git/` and local environment. Your existing local SQLite database is retained; the next development API startup applies pending migrations automatically.

## What changed

- Development startup now applies the repository's Alembic migration chain instead of calling `Base.metadata.create_all()` directly.
- Alembic uses the same engine factory as the application. SQLite parent directories are created; SQLite connections enable foreign keys and a bounded busy timeout.
- PostgreSQL URLs are normalised to the pinned `postgresql+psycopg` driver and use pre-ping, bounded pool settings and connection timeout.
- `/health/ready` now reports database dialect and current/expected migration revision. A schema that is missing or behind the current head prevents readiness.
- The original initial migration remains unchanged. New revision `20261109_0002` installs pgvector on PostgreSQL.
- Added `scripts/verify_database.py` for migration/table/extension checks.
- Added a PostgreSQL 17 + pgvector service job in GitHub Actions. Its hosted run must be checked after pushing; it was not run from the authoring environment.
- Updated Phase 02 status, architecture, validation, provenance and setup documentation.

## Verify locally — Windows PowerShell

Activate your existing environment and run from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python scripts/verify_database.py
python -m compileall -q backend apps tests scripts
pytest
python scripts/evaluate_golden_cases.py
```

For a fresh local checkout, create the virtual environment and install dependencies first as described in `README.md`. Build 010 does not change frontend source; the participant should still run the final frontend lint/typecheck/build on the final checkout before submission.

## Optional PostgreSQL + pgvector test

The existing `.env` is intentionally not overwritten by this archive. To try PostgreSQL locally, add a `POSTGRES_PASSWORD` setting to `.env`, start the service, then change `DATABASE_URL` to a matching URL:

```powershell
docker compose -f infra/docker-compose.yml --profile infra up -d db
python -m alembic upgrade head
python scripts/verify_database.py
```

Use a development-only password. Do not expose the database port publicly or reuse local credentials in production.

## Validation in the authoring environment

- **72 backend tests passed** against SQLite/local configuration.
- Fresh temporary SQLite migration: upgrade to head and repeat upgrade passed.
- Database verifier: current revision `20261109_0002`, all eight mapped application tables present.
- SQLite foreign-key enforcement and PostgreSQL URL normalisation tests passed.
- Python compilation and CI YAML parsing passed.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** across 12 synthetic cases.
- Live PostgreSQL/pgvector, live MinIO/AWS and Ruff lint were not run in this environment.
- PostgreSQL CI job is configured but its hosted result is pending.
- Frontend files were unchanged; frontend checks were not rerun for Build 010.

See `BUILD_010_MANIFEST.json` and `docs/technical/BUILD_010_DATABASE_LIFECYCLE.md` for the detailed scope and evidence.
