# Phase 02 — Repository, runtime and engineering foundation

**Phase objective:** create a reproducible modular monolith with clean domain, application and infrastructure boundaries.

## Deliverables and current evidence

- [x] Monorepo layout for web, API, worker scaffold, modules, fixtures, tests, migrations, docs and infrastructure.
- [x] README, environment example, setup instructions, architecture notes and local startup/test scripts.
- [x] FastAPI `/api/v1`, request IDs, CORS and structured errors.
- [x] Health/liveness and readiness endpoints; readiness verifies the active Alembic migration head.
- [x] SQLAlchemy models and forward-only Alembic migration chain.
- [x] SQLite local runtime with FK enforcement; PostgreSQL URL/psycopg engine path and pool controls.
- [x] `scripts/verify_database.py` checks expected revision, mapped tables and PostgreSQL pgvector extension.
- [x] Object storage boundary for private local and opt-in S3-compatible storage, with authenticated SHA-256 verified original downloads.
- [x] Next.js App Router, TypeScript and design tokens in frontend source.
- [x] Unit/integration tests and labelled golden evaluation script.
- [x] PostgreSQL 17 + pgvector service job defined in CI; hosted job result not yet observed.
- [x] SQLite-mode backend suite and fresh SQLite migration upgrade/repeat-upgrade tests pass in Build 010 authoring environment.
- [ ] Hosted PostgreSQL/pgvector CI result, live MinIO/S3 run and complete deployment/recovery evidence.

## Current verification evidence

- Backend unit/integration suite: **72 passing tests** in the Build 010 authoring environment.
- Database verifier: SQLite schema at migration head `20261109_0002`; all eight required application tables present.
- Python compilation: passed.
- Synthetic golden corpus: **11 PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL**.
- Frontend: participant-confirmed lint, typecheck and production build passed on Windows (2026-11-08); frontend source was not changed in Build 010.

## Gate decision

**Gate status: PARTIALLY COMPLETE.** The local migration lifecycle is now migration-driven and readiness detects an out-of-date schema. The PostgreSQL/pgvector integration is wired into CI but remains unverified until the hosted job runs successfully. Live object-storage integration, durable workflow execution, production tenant isolation and clean deployment evidence also remain open. Phase 02 is not represented as production-ready.
