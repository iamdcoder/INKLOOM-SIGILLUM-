# Inkloom Sigillum — Build 017 patch handoff

**Build:** 017 (cumulative, based on Build 016)  
**Phase:** 05 — Secure submission, storage and immutable content versions  
**Implementation status:** Complete in local code and tests; external operational acceptance remains pending. See `docs/phase-gates/PHASE-05-STATUS.md`.

## Delivered

1. Guided, resumable drafts with publication context, edit/cancel and draft resume.
2. Creator/Agency-only submission, upload, cancellation and revision actions.
3. PDF, DOCX, TXT, PNG and JPG/JPEG validation for extension, file signature/container, MIME and resource limits.
4. Fail-closed ClamAV scanning before content extraction and durable storage.
5. SHA-256 duplicate lookup, client progress, explicit duplicate confirmation and idempotent staged upload retry.
6. Immutable local filesystem and conditional S3 object writes.
7. Content-version scan/retention metadata and parent-version lineage.
8. Transactional `ReviewRun` context and durable `ReviewJob` rows for each successful upload.
9. Migration `20261109_0006` for intake/version/job records and `20261109_0007` for retention metadata.
10. Integration/unit regressions for the happy path, retries, format validation, scanner failures, role boundaries, version lineage and storage immutability.

## Verification

- **146 passed, 2 skipped, 0 failed** (148 tests collected).
- Python compilation passed.
- SQLite migration head `20261109_0007`; schema verifier has no missing required tables.
- Golden evaluation: 11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL.
- TypeScript compiler API syntax parse passed for 17 frontend files.
- Frontend lint/typecheck/production build not verified because the dependency installation is incomplete in this environment.
- PostgreSQL RLS/concurrency, live ClamAV, live S3/MinIO and browser E2E are pending external verification.

## Important boundaries

- Infected upload bytes are rejected before object-store persistence; only blocked request and audit metadata are retained. There is no separate binary quarantine bucket.
- Review jobs are transactionally persisted but run inline in Phase 05. Independent worker leases/checkpoints/replay and SSE progress are Phase 11.
- Retention due dates are recorded, but automatic purge/object-orphan reconciliation is deferred.
- Full scanned-PDF OCR and embedded PDF/DOCX image-region extraction are Phase 06 work.
- Live scanner and PostgreSQL behaviour must not be described as verified until the corresponding external CI/service checks pass.

Build 017 is the baseline for Phase 06 — Document parsing, OCR and visual-region extraction.
