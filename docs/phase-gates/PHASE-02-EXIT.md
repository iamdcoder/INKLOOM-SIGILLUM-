# Phase 02 — Repository, runtime and engineering foundation

**Phase objective:** create a reproducible modular monolith with clean domain, application and infrastructure boundaries.

## Deliverables and current evidence

- [x] Monorepo layout for web, API, worker scaffold, modules, fixtures, tests, migrations, docs and infrastructure.
- [x] README, environment example, setup instructions, architecture notes and local startup/test scripts.
- [x] FastAPI `/api/v1`, request IDs, CORS and structured errors.
- [x] Health/liveness and readiness endpoints.
- [x] SQLAlchemy models and initial Alembic migration.
- [x] SQLite local demo persistence and private filesystem source storage.
- [x] Pydantic request/response validation and OpenAPI endpoints.
- [x] Next.js App Router, TypeScript, React and design tokens in frontend source.
- [x] Unit/integration tests and labelled golden evaluation script.
- [ ] Clean-checkout migration execution, CI migration job and smoke test retained as evidence.
- [ ] Frontend dependency installation and `npm run build` verified; package lockfile retained.
- [ ] CI workflow with formatting, lint, typecheck, migration and smoke tests.
- [ ] PostgreSQL/pgvector and MinIO adapters connected and tested; Compose currently remains a scaffold.
- [ ] Worker process, durable job table/leases and workflow checkpoints implemented; reviews currently execute synchronously.

## Current verification evidence

- Python test suite: **27 passing tests** in the recorded development environment.
- Synthetic golden corpus: **11 automated PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL**.
- Python compilation: run `python -m compileall -q backend apps tests scripts` before release.
- Frontend: not build-verified; run `npm install` and `npm run build` locally before describing it as build-successful.

## Gate decision

**Gate status: PARTIALLY COMPLETE.** Core API/runtime, database schema, local storage, extraction, deterministic checks and frontend source exist. Production infrastructure, CI, active worker/orchestration, Postgres/pgvector/MinIO integration and a verified frontend build remain incomplete. This phase currently supports a local MVP demo, not a production-ready platform.
