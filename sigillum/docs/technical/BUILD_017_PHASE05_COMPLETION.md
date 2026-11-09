# Build 017 — Phase 05 implementation record

**Product:** Inkloom Sigillum  
**Build:** 017  
**Baseline:** Build 016  
**Phase:** 05 — Secure submission, storage and immutable content versions  
**Migration head:** `20261109_0007`

## 1. Outcome

Build 017 closes the Phase 05 implementation scope with a real staged submission path, not a disconnected upload screen. Publication context is saved as a draft first. The browser then computes a SHA-256 digest, checks for existing matching content, requests explicit confirmation for duplicates, and uploads the selected asset with a reusable idempotency key. Server validation and the malware scan run before extraction or object storage.

The existing `POST /api/v1/submissions` multipart endpoint remains available for backwards compatibility. Clients should send `Idempotency-Key` when using this single-request endpoint; the staged browser flow always sends an idempotency key.

## 2. API and UI changes

### New/extended API endpoints

- `POST /api/v1/submissions/drafts` — create an unsubmitted draft.
- `PATCH /api/v1/submissions/{id}/draft` — edit publication context while it remains a draft with no current version.
- `DELETE /api/v1/submissions/{id}` — cancel only an unsubmitted draft.
- `POST /api/v1/submissions/duplicate-check` — check CLEAN versions by SHA-256 within the actor's permitted workspace scope.
- `POST /api/v1/submissions/{id}/content` — submit the first immutable version for a saved draft.
- `POST /api/v1/submissions/{id}/revisions/upload` — upload a scanned immutable revision linked to the previous version.
- `POST /api/v1/submissions` — backwards-compatible one-request upload with optional explicit idempotency key.

Only Creator and Agency workspace roles can create/update/cancel drafts, upload submissions or create revisions. Reviewer, Brand Owner and Administrator actions remain in their own workflow areas by default.

### Browser flow

`apps/web/app/submissions/new/page.tsx` now supports:

1. Draft create/update and resume through `/submissions/new?draft={id}`.
2. PDF/DOCX/TXT/PNG/JPG selection with drag/drop and browse.
3. Client file-size/extension checks; the server remains authoritative.
4. SHA-256 duplicate check and confirmation before intentionally uploading a matching file again.
5. XMLHttpRequest upload progress and abort control.
6. Idempotency key persisted in `sessionStorage` for the draft+file digest, so a network retry reuses the same key.
7. Draft preservation after a cancelled/failed upload; only explicit discard cancels a draft.

The submissions list shows saved drafts and a resume action. The file remove action is outside the label/file-picker surface to avoid nested interactive controls.

## 3. Secure intake pipeline

The server repeats all important validation. It reads at most `MAX_UPLOAD_BYTES + 1` bytes (default `MAX_UPLOAD_BYTES=10485760`, 10 MiB) and validates:

- Allowlisted file extension and sanitized display filename.
- Format signature and container structure; PDF encryption and page count.
- DOCX ZIP structure, required document part, archive entry count, expanded size, CRC, macro payloads and unsafe archive paths. External relationship targets are never fetched.
- PNG/JPEG format, actual dimensions, pixel ceiling and Pillow decompression-bomb protections.
- UTF-8 text validity for TXT.
- Declared MIME type against the type derived from file content (generic octet-stream declarations are treated as unspecified).

After structural validation, the ClamAV adapter scans the in-memory bytes through `INSTREAM`. Only a CLEAN result continues. INFECTED is recorded as BLOCKED and returns `MALWARE_DETECTED`; unavailable, errored, invalid or throwing scanner states return `MALWARE_SCANNER_UNAVAILABLE`. No object or content version is created unless the scanner confirms CLEAN.

**Quarantine behaviour:** infected bytes are not written to the regular object store or a separate quarantine bucket. Only the idempotency request's blocked state and audit metadata are retained. This is intentionally safer than retaining untrusted malware binaries, but is a narrower implementation than a segregated binary quarantine store.

## 4. Immutable storage and records

Successful original files are written under an opaque key in the tenant/brand/submission namespace, with a UUID object name and validated suffix. The local adapter uses a private atomic create and refuses to overwrite an existing object. The S3-compatible adapter uses conditional `IfNoneMatch="*"` writes.

The content version stores:

- SHA-256, size, server-derived MIME, safe display filename and storage key.
- Creator/uploader, scan status/engine/time/signature and extraction metadata.
- Optional `parent_version_id` for revision lineage.
- Retention policy and optional `retention_until` timestamp.

Downloads require an authorised session, a CLEAN scan state and a fresh SHA-256 check of the stored bytes. Storage keys are not returned to the browser.

## 5. Idempotency, review context and jobs

`submission_upload_requests` reserves an idempotency key, scoped to tenant, brand and actor. The unique constraint prevents concurrent requests from both reserving the same key. A repeated request with the same file returns the stored completed result; reuse for a different file is rejected.

A successful upload creates the following records in one transaction:

1. New immutable `ContentVersion`.
2. `ReviewRun` in QUEUED state with exact content hash, Knowledge Pack fingerprint/version, and immutable Knowledge Pack snapshot.
3. `ReviewJob` in QUEUED state with the publication context snapshot and content-version reference.
4. Upload-request linkage to the content version and review context.

The request process then moves the durable job through RUNNING to COMPLETED/FAILED and invokes the existing review service. This preserves a transactional job record but does **not** implement the independent leased worker/checkpoint/replay path planned for Phase 11.

## 6. Database changes

- `20261109_0006_secure_submission_intake.py`: publication context columns, parent/scan metadata, `submission_upload_requests`, `review_jobs`, uniqueness, lookup indexes and PostgreSQL RLS policies.
- `20261109_0007_content_retention_metadata.py`: `retention_policy` and `retention_until` on content versions.

The schema verifier confirms SQLite migration head `20261109_0007` and all required tables. SQLite reports RLS as not applicable. PostgreSQL behaviour remains pending its dedicated CI job.

## 7. Tests added/extended

Coverage includes:

- Staged draft, upload, retry, duplicate lookup and durable job/review linkage.
- Deterministic same-draft retry when a client omits an idempotency header; explicit-key support for the legacy endpoint.
- Different content under a reused key rejected.
- Draft context update/cancel and Creator/Agency role guard.
- Unsupported signature and declared-MIME mismatch rejected.
- Infected, unavailable and throwing scanner outcomes fail closed before content version creation.
- PDF/DOCX/TXT/PNG/JPG end-to-end upload coverage.
- JPEG MIME, scan and hash metadata.
- DOCX Windows/traversal archive path rejection.
- Parent-version linkage and CLEAN scan metadata on revisions.
- Immutable local/S3 adapter writes and original-download integrity.

## 8. Verification results

| Check | Result |
|---|---|
| Pytest | **146 passed, 2 skipped, 0 failed** (148 collected) |
| Skipped tests | PostgreSQL RLS and concurrent version/publication locking; they are configured for the PostgreSQL CI job |
| Python compileall | Passed |
| Alembic | Current at `20261109_0007` |
| SQLite schema verifier | No missing required tables; RLS not applicable to SQLite |
| Golden evaluation | 11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL |
| TypeScript compiler API parse | 17 frontend `.ts` / `.tsx` files; zero syntax diagnostics |
| Frontend lint/typecheck/build | **Not verified**; dependency tree incomplete, offline install missing a cached package, and type definitions not resolved |
| Live PostgreSQL / ClamAV / S3 / browser E2E | **Not run** in this authoring environment |

API integration tests inject a deterministic clean scanner to exercise the API flow. The separate malware scanner unit tests exercise the ClamAV protocol and scanner status mapping. Those tests are not a substitute for a live ClamAV daemon/signature-update test.

## 9. Operational setup and outstanding work

For local development, configure `CLAMAV_HOST`, `CLAMAV_PORT` and `CLAMAV_TIMEOUT_SECONDS`, then start the Compose scanner service with:

```powershell
docker compose --profile security up -d clamav
docker compose ps clamav
```

When the API runs on the host, use `CLAMAV_HOST=127.0.0.1`; when it runs inside the same Compose network, use `CLAMAV_HOST=clamav`. Wait for the signature database to finish updating. There is no scan bypass.

Before describing this build as operationally accepted, run and retain evidence for:

1. PostgreSQL CI: RLS negative-access tests and concurrent version allocation.
2. Live ClamAV: a clean file, an EICAR test signature, outage and recovery.
3. Frontend: clean `npm ci`, `npm run lint`, `npm run typecheck`, `npm run build`.
4. Browser walk-through: draft save/reload, drag/drop, duplicate confirmation, progress, abort/retry and submission review.
5. A real S3/MinIO conditional create/download test if that storage backend will be used.

`CONTENT_RETENTION_DAYS=0` is the default MANUAL policy. A positive value only records a configured retention timestamp. Automated purge, storage-orphan cleanup and a retained-binary quarantine store are not implemented here.

## 10. Next phase

Build 017 becomes the new baseline. Phase 06 is **Document parsing, OCR and visual-region extraction**; it should build on the stable immutable source versions and storage references delivered here.
