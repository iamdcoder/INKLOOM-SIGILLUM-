# Inkloom Sigillum — Build 015

**Baseline:** Build 014  
**Phase:** 04 — Brand Control Center and Knowledge Pack lifecycle  
**Status:** Phase 04 remains open; this is a cumulative source snapshot, not a claim of full phase sign-off.  
**Alembic head:** `20261109_0005`

## What changed

Build 015 adds owner-configurable asset usage policies to the Brand Control Center. The policy editor writes into a Knowledge Pack draft; the rules do not become authoritative until the draft is validated and published by an authorised Brand Owner.

Per asset kind (`logo`, `product_image`, `campaign_image`, `icon`, `other`), owners can configure:

- Allowed brand channels and declared use-cases.
- Minimum width and height in pixels.
- An allowed palette of six-digit RGB hex values.
- RGB-distance tolerance and minimum weighted palette coverage.
- Policy validity start/end and severity.
- A clear-space ratio that explicitly requires human inspection.

Newly uploaded raster brand assets receive a bounded, thumbnail-derived weighted palette. Palette enforcement uses RGB Euclidean distance and is a rough deterministic screen only; it is not perceptual colour difference, ICC-aware colour management, logo identity recognition or semantic brand-fit certification. If a policy requires a palette but an older asset has none, validation returns `ASSET_PALETTE_UNMEASURABLE` rather than pretending it measured a 0% match. Non-zero clear-space policy remains manual review.

Submissions now carry a controlled `intended_use` field. It is stored on the submission and shown in review context. Review-time channel/use/validity restrictions are applied only when an uploaded image has an exact SHA-256 match to an approved catalogue asset. This version does not recognise a logo embedded inside a different flattened creative and does not use perceptual similarity as decisive evidence.

Migration `20261109_0005_submission_intended_use` adds non-null `submissions.intended_use` with `general` default. It handles both fresh SQLite schema bootstrap and existing Build 014 database schemas.

## Upgrade from Build 014

1. Back up the current repository, `.env`, `data/`, and the database.
2. Extract Build 015 over the existing project source.
3. Preserve `.env`, `.git`, `.venv`, `node_modules`, local `data/`, and any private original uploads.
4. Activate the existing virtual environment and run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python scripts/verify_database.py
pytest -q
python scripts/evaluate_golden_cases.py
```

The migration is forward-compatible for the current SQLite and PostgreSQL migration paths. Do not edit the database manually to add `intended_use`.

## Verification performed in this authoring environment

- Backend tests: **119 passed, 1 skipped, 0 failed (120 collected)**.
- The one skipped test is PostgreSQL-only RLS enforcement; local tests ran on SQLite.
- Python compileall: passed for `backend`, `apps`, `migrations`, `tests` and `scripts`.
- Database verifier: SQLite current at `20261109_0005`; all 16 required tables present.
- Golden evaluation: **11 PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL** across 12 deterministic synthetic cases.
- TypeScript compiler API syntax parsing passed for `apps/web/app/brand/page.tsx`, `apps/web/app/submissions/new/page.tsx`, `apps/web/app/reviews/[id]/page.tsx` and `apps/web/lib/api.ts`.
- Full frontend dependency installation timed out. Consequently `npm run lint`, `npm run typecheck` and `npm run build` are **not verified** for this build.
- Live PostgreSQL RLS/concurrency, live ClamAV, live MinIO/AWS and browser E2E were not run.

## Remaining Phase 04 work

- Live PostgreSQL RLS and concurrent publication tests with a non-superuser application role.
- Live ClamAV Compose integration and signature database readiness test.
- Guided forms for facts, policies, terminology and voice.
- Broader conflict validation and source replacement/version lifecycle.
- Retention/deletion and orphaned object cleanup.
- Perceptual asset matching as a candidate signal with required human confirmation.
- Full frontend checks and browser walkthrough.

See `docs/phase-gates/PHASE-04-STATUS.md` and `docs/technical/BUILD_015_ASSET_USAGE_POLICIES.md`.
