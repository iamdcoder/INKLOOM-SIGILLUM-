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
- [x] Live HTTP vertical-slice smoke test executed with 8 passing checks; report retained under `reports/live_vertical_slice_smoke_latest.json`.
- [ ] Clean-checkout migration execution and CI migration job retained as evidence.
- [x] Participant Windows frontend dependency install, `npm run lint`, `npm run typecheck` and `npm run build` passed; retain and commit the participant-generated package lockfile.
- [ ] CI workflow with formatting, lint, typecheck, migration and smoke tests.
- [ ] PostgreSQL/pgvector and MinIO adapters connected and tested; Compose currently remains a scaffold.
- [ ] Worker process, durable job table/leases and workflow checkpoints implemented; reviews currently execute synchronously.

## Current verification evidence

- Python test suite: **27 passing tests** in the recorded development environment.
- Synthetic golden corpus: **11 automated PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL**.
- Python compilation: run `python -m compileall -q backend apps tests scripts` before release.
- Frontend: participant-confirmed lint, typecheck and production build passed on Windows (2026-11-08).

## Gate decision

**Gate status: PARTIALLY COMPLETE.** Core API/runtime, database schema, local storage, extraction, deterministic checks and frontend source exist. Production infrastructure, CI, active worker/orchestration and Postgres/pgvector/MinIO integration remain incomplete. The local MVP is demonstrable but is not production-ready. This phase currently supports a local MVP demo, not a production-ready platform.
