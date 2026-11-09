# Inkloom Sigillum — Build 013 handoff

**Build:** 013  
**Baseline:** Build 012 (cumulative source snapshot; includes Builds 001–012)  
**Milestone:** Phase 04 — Brand Control Center and Knowledge Pack lifecycle  
**Phase status:** Partially implemented; not signed off  
**Date:** 2026-11-09

## What changed in Build 013

Build 013 closes the major persistence and concurrency gap in the Knowledge Pack lifecycle without changing the current API's core workflow.

1. **Transactional catalogue.** Added database tables for tenant+brand active pack heads, immutable Knowledge Pack version snapshots, drafts and per-record decisions.
2. **Alembic migration.** Added `20261109_0004_brand_knowledge_catalog.py`, including PostgreSQL RLS policies for each new table.
3. **Database authority.** The database is now authoritative for active version, snapshots, drafts, validation and owner record decisions. Existing filesystem JSON files remain compatibility/export mirrors; private binary assets remain in the configured storage adapter.
4. **Concurrency protection.** Draft writes use revision compare-and-swap. Publication locks the active head/draft on PostgreSQL and conditionally advances the head with its current version/revision. Stale writes/publications fail explicitly instead of overwriting newer state.
5. **Build 012 data recovery.** On first scoped access, the full published Build 012 filesystem version history is imported into the DB after each snapshot fingerprint and the active-pointer fingerprint are validated. Eligible un-published Build 012 filesystem drafts are imported once into the new draft table; malformed files are left untouched.
6. **Decision history.** Owner decisions are persisted to an append-only table with decision status, reason, actor and timestamp. Added `GET /brands/current/drafts/{draft_id}/decisions`, scoped to the selected brand.
7. **Database verifier.** `scripts/verify_database.py` now checks the four new tables and their PostgreSQL RLS policy coverage.
8. **Historical migration correctness.** Froze the original `20261108_0001` schema boundary so fresh migrations do not accidentally create tables that belong to later revisions.
9. **Regression evidence.** Added tests for database reload across store instances, stale draft compare-and-swap, filesystem draft recovery, decision history and the new migration tables.

## Verification performed

- Backend suite: **99 passed, 1 skipped** (100 collected). The skip is the PostgreSQL-only RLS runtime test; a PostgreSQL service is unavailable in this authoring environment.
- Python compilation: `python -m compileall -q backend apps migrations tests scripts` — passed.
- Alembic/database: fresh/repeatable migration passes; SQLite is current at `20261109_0004`; all 16 required tables are present.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** across 12 synthetic cases. The visual asset/contrast fixture remains manual review by design; this is not a general accuracy claim.
- Frontend: no frontend source was changed in Build 013. Full lint/typecheck/build remain unverified for the cumulative Build 011/012 UI changes.
- PostgreSQL RLS/concurrent publication and live MinIO/AWS storage remain unverified.

## Phase 04 still open

- Live non-superuser PostgreSQL RLS and row-lock/concurrency validation.
- Controlled PDF/DOCX source-document import with retained page/paragraph provenance.
- Malware scanning/quarantine for uploads.
- Owner-configurable asset use, dimensions, palette, clear-space, scope and validity enforcement.
- Guided create/edit forms, stronger normalized schemas and conflict checks.
- Owner-visible detailed version comparison/change summary.
- Browser walkthrough evidence and full frontend quality gates.

See `docs/phase-gates/PHASE-04-STATUS.md` and `docs/technical/BUILD_013_KNOWLEDGE_CATALOG.md` for technical details and evidence.

## Apply this cumulative build

1. Back up the current repository, `data/` directory and database.
2. Extract `Sigillum_Build_013.zip` over the existing repository root.
3. Preserve local `.env`, `.git`, `data/`, `.venv/` and `apps/web/node_modules/`; these are not included in the archive.
4. Activate your existing Python virtual environment. Install only if package requirements changed (Build 013 adds no Python runtime dependency).
5. Run the migration, verifier and tests below.

```powershell
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python scripts/verify_database.py
pytest -q
python scripts/evaluate_golden_cases.py
python -m compileall -q backend apps migrations tests scripts
```

The expected migration head is now `20261109_0004`. Back up the database before applying it. The migration is forward-only in the normal build path; do not delete or recreate an existing database to apply this update.

For the frontend, from `apps/web`:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```

Build 013 has no frontend source changes, but those checks are still required for the cumulative Build 011/012 frontend code.

## Integrity and scope

The archive is a cumulative source snapshot. It excludes `.git`, `.env` files, local databases, user uploads, virtual environments, `node_modules`, build caches and Python bytecode. Do not apply it as a separate second patch on top of another Build 013 copy.

**Definition of done for this increment:** the Knowledge Pack active pointer, immutable snapshots, drafts and per-record decisions are transactionally persisted; stale writes/publications are guarded; legacy filesystem version history and drafts are recoverable; the regression suite passes. **Definition of done for Phase 04 is not met yet**; see the phase-gate status.
