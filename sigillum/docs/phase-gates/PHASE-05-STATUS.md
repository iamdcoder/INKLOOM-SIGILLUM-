# Phase 05 — Secure submission, storage and immutable content versions

**Build:** 017  
**Baseline:** Build 016  
**Implementation status:** Complete in the local codebase and covered by local Python tests.  
**External operational acceptance:** Pending PostgreSQL, live ClamAV, and browser/frontend verification.

## Scope and acceptance map

| Master-plan requirement | Implementation | Evidence / status |
|---|---|---|
| Guided submission context | Draft captures title, brand/workspace context, channel, locale, geography, audience, offer, intended use, product/campaign scope, optional note and timezone-aware publication time. | API create/update draft routes; resumable UI source; API integration tests. |
| PDF, DOCX, TXT, PNG and JPG | Server chooses the parser from the sanitized extension and validates bytes/container before use. | PDF/DOCX/TXT/PNG/JPG integration coverage; JPEG upload regression added in Build 017. |
| Drag/drop and browse | Native file input with drop target; client extension/size checks; server repeats validation. | `apps/web/app/submissions/new/page.tsx`; TSX syntax parse only, browser interaction not yet exercised here. |
| Draft creation, cancellation and recovery | Draft is committed before upload, can be updated/resumed, and can be cancelled only before a version exists. Aborted/network-failed browser uploads keep the draft. | API tests cover update/cancel and retry. Browser crash/reload recovery is implemented through draft URL and server record, not a browser E2E-tested claim. |
| Progress and duplicate warning | XHR upload progress; SHA-256 via Web Crypto; scoped duplicate lookup; explicit confirmation for matching versions. | Frontend source inspection and TypeScript syntax parse. Runtime browser verification pending. |
| Extension/MIME/signature validation | Allowlisted extension, format signature/container parse and declared MIME comparison (generic octet-stream is accepted as an unspecified browser MIME). | Unit and integration tests including signature and MIME mismatch. |
| Resource limits | Default 10 MiB upload limit; PDF page cap; DOCX member/expanded-size ceilings and CRC check; image pixel ceiling and decompression-bomb handling. | `sniff_file` validation code and unit/integration coverage. Deployment settings can raise/lower the byte limit. |
| Malware scan before extraction/storage | ClamAV `INSTREAM` scan occurs before document extraction and durable object storage. Only CLEAN proceeds; INFECTED, UNAVAILABLE, invalid and throwing scanner outcomes fail closed. | Scanner protocol unit tests plus injected-clean/infected/unavailable/exception API tests. Live ClamAV daemon test pending. |
| Private immutable storage | Opaque UUID object keys, local atomic no-overwrite writes, S3 conditional PUT, SHA-256/size/MIME/safe filename metadata, integrity-checked authenticated download. | Local and fake-S3 adapter tests, upload/download integrity tests. Live MinIO/S3 endpoint not verified. |
| Version lineage | Each upload creates a new content version; revision and accepted TXT patch link to the parent version. | Version history and patch/revision integration tests. |
| Durable review context and job | Version, immutable Knowledge Pack snapshot, QUEUED `ReviewRun`, and QUEUED `ReviewJob` are committed together before execution. | Database assertions in resumable upload test. Review currently runs inline; leased worker/checkpoint/SSE behaviour is Phase 11. |
| Access control | Only Creator and Agency roles can create/update/cancel drafts, submit, or create revisions. Creator/Agency resource access remains limited to owned submissions. | Role-denial and workspace-scope tests. PostgreSQL RLS remains externally unverified. |
| Retention metadata | `CONTENT_RETENTION_DAYS=0` stores MANUAL retention; positive values store a configured policy label and due timestamp. | Migration `20261109_0007` and model/config tests. Automatic purge is deferred. |

## Phase 05 gate result

**Local implementation gate: PASS.**

- 148 tests collected: 146 passed, 2 skipped, 0 failed.
- Python `compileall` passed.
- SQLite Alembic head is `20261109_0007`; schema verifier reports no missing required tables.
- Golden evaluation: 11 PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL.
- TypeScript compiler API syntax parse passed for 17 `.ts`/`.tsx` files.

**External operational gate: PENDING.**

| Check | State | Notes |
|---|---|---|
| PostgreSQL RLS on `submission_upload_requests` and `review_jobs` | Pending | SQLite cannot verify row-level security. Existing PostgreSQL CI tests cover RLS and row-lock concurrency; retain their passing run. |
| Concurrent version allocation | Pending | `SELECT ... FOR UPDATE` is present. The real concurrent test requires PostgreSQL and is skipped on SQLite. |
| Live ClamAV submission scanning | Pending | Local API integration tests inject scanner results. Start the security Compose profile and verify CLEAN/EICAR/unavailable behaviour with the actual daemon. |
| Frontend lint, typecheck and production build | Pending | `npm ci --offline` failed because a package was not cached; current `node_modules` is incomplete. Global `tsc --noEmit` could not resolve missing `@types` packages. |
| Browser walkthrough | Pending | No browser-level drag/drop, progress, draft-reload or cancellation E2E run was performed. |
| Live S3/MinIO | Pending | Conditional object create is unit-tested with a fake S3 client; no external object store was run. |

## Deliberate deferrals / boundaries

1. Infected upload bytes are rejected before object-store persistence. The upload-request status and security audit metadata are retained; there is no separate malware-binary quarantine bucket in this build.
2. ReviewJob is a durable transactional outbox record, but Phase 05 invokes the review synchronously in the request process. Worker leases, retries, checkpointing, cancellation semantics and SSE/polling replay belong to Phase 11.
3. `retention_until` is recorded but no scheduled object/database purge or orphan-reconciliation worker is implemented.
4. OCR and visual analysis remain at the current Phase 06 capability level. This phase does not claim embedded PDF/DOCX image extraction, scanned-PDF OCR, or automatic logo identity certification.
5. `CONTENT_RETENTION_DAYS=0` is the default and means MANUAL retention. A positive value records the configured expiry metadata only; it does not automatically delete content.

## Next phase

Build 017 is the baseline for **Phase 06 — Document parsing, OCR and visual-region extraction**. Do not start Phase 06 until the external checks above are documented or explicitly accepted as deployment-time gates.
