# Inkloom Sigillum — Build 009 Patch

**Base:** Build 008  
**Increment:** Private Object Storage Boundary and Integrity-Checked Downloads  
**Date:** 2026-11-09

## Apply

This is the next full project snapshot. Back up your current `sigillum` folder, then extract the archive over a copy of the repository root while preserving folder paths. It contains the source, tests and documentation state from Build 009. Local `.env` files, local databases, object uploads, `.venv`, `node_modules` and `.next` are intentionally not packaged.

The source `.git` directory is included to preserve the repository's actual history. Build 009 modifications are not represented as a fabricated commit; inspect `git status` and make a commit using your own verified identity after review.

No database schema migration is required for Build 009.

## What changed

- Add `backend/sigillum/infrastructure/storage/` with `ObjectStorage`, local filesystem and S3-compatible implementations.
- Configure the adapter using `STORAGE_BACKEND`; local remains the default.
- Integrate object storage into original version writes, authenticated download, and readiness.
- Verify SHA-256 on every original-file download; modified/corrupted object bytes are not returned.
- Map object-storage outages to a distinct 503 `STORAGE_UNAVAILABLE` response.
- Add storage unit tests and API regression tests for upload/download integrity and outage handling.
- Update README, architecture, Phase 02 status, provider register, AI/reuse disclosure and build log.

## Verify backend (PowerShell, repository root)

```powershell
.\.venv\Scripts\Activate.ps1
python -m compileall -q backend apps tests scripts
python -m pytest -q
python scripts/evaluate_golden_cases.py
```

Expected in the authoring environment for this archive:

- Storage unit suite: **14 passed**
- Backend suite: **66 passed**
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**
- Live HTTP vertical slice: **9/9 checks passed**, including original download hash verification (`reports/build009_live_smoke_verification.json`)

These results are local automated tests, not a claim that live MinIO, AWS S3, PostgreSQL or pgvector integration has been externally validated. Ruff lint was not run here because Ruff is not installed in the authoring environment.

## Verify frontend

Build 009 does not change frontend files. Frontend lint/typecheck/build were not rerun here. Run these on your Windows checkout:

```powershell
cd apps\web
npm run lint
npm run typecheck
npm run build
```

## Optional S3-compatible mode

Set `STORAGE_BACKEND=s3` and configure endpoint, bucket, region and credentials in `.env`. Development mode may create a missing bucket when permissions allow. Production bucket provisioning, TLS, encryption, retention and backup remain infrastructure responsibilities. The checked-in `.env.example` keeps local filesystem storage as the default.
