# Build 009 — Object storage boundary and original-file integrity

**Date:** 2026-11-09  
**Base:** Build 008  
**Phase:** 02 — Repository, runtime and engineering foundation  
**Gate:** Phase 02 remains IN PROGRESS.

## Why this increment

The prior API wrote original binaries directly under `STORAGE_ROOT` and the download route assumed that same local path. That prevented the application from switching binary storage independently from the review domain and made readiness too weak to verify the actual configured storage capability.

Build 009 introduces an `ObjectStorage` port so application services no longer manipulate storage paths directly.

## Delivered

- `LocalFilesystemStorage`: private local adapter with opaque relative POSIX keys, traversal and symlink-escape checks, atomic temporary-file writes, restrictive file/directory permissions and a write/readiness probe.
- `S3CompatibleStorage`: boto3 adapter for S3-compatible APIs. It supports a configured endpoint, bucket, region, credentials, TLS verification, bounded connection/read timeouts and SDK retry configuration.
- `get_storage(settings)`: process-level adapter selection controlled by `STORAGE_BACKEND` (`local` by default, `s3` when explicitly configured). Local readiness performs a write probe; S3 readiness checks bucket reachability and does not prove that every configured object permission is granted.
- `ReviewService.create_version`: stores original bytes through the adapter after parsing and hashing; it no longer constructs filesystem paths.
- Authenticated download route: fetches through the adapter, recomputes SHA-256 and refuses to return bytes whose hash differs from the immutable version record. Responses include private/no-store caching and `nosniff`.
- Distinct `STORAGE_UNAVAILABLE` API failure for object-store outages; a storage outage is no longer misreported as a parsing failure.
- Readiness separately reports database, storage driver and Brand Knowledge Pack availability.
- Development-only bucket bootstrap for S3-compatible mode. Production bucket creation remains an infrastructure responsibility.

## Configuration

Default local mode needs no extra configuration:

```dotenv
STORAGE_BACKEND=local
STORAGE_ROOT=./data/private_uploads
```

Optional S3-compatible mode:

```dotenv
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=http://127.0.0.1:9000
S3_BUCKET=sigillum-private
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=sigillum
S3_SECRET_ACCESS_KEY=replace-with-a-local-secret
S3_VERIFY_SSL=true
```

Do not deploy the example MinIO credentials. Provision a private bucket and restrict credentials to the required bucket/object operations. For production, use a secret manager or workload identity where supported, TLS, encryption at rest, lifecycle/retention policies and backups. Sigillum does not claim to configure all of those provider-level controls automatically.

## Verification performed in the authoring environment

- Storage unit suite: 14 passed.
- Full backend unit/integration suite after this increment: 66 passed.
- Golden evaluation: 11 PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL (same included synthetic cases).
- Python `compileall`: recorded separately in the Build 009 manifest.
- S3 adapter tests use an offline fake S3 client; they test adapter mapping/behaviour without network access.
- Live HTTP vertical slice: 9 checks passed against an isolated SQLite/local-storage API, including authenticated original-file download and SHA-256 verification (`reports/build009_live_smoke_verification.json`).
- No live MinIO, AWS S3, PostgreSQL or pgvector server was available for an external-service integration test.
- Frontend code was not modified in Build 009; frontend lint/typecheck/build was not rerun for this increment.

## Known boundaries

- Local adapter is suitable for private development/offline demos, not a distributed multi-process storage service.
- No object deletion lifecycle, retention scheduler, malware scanning or provider-side encryption policy is provisioned by this build.
- S3 `ensure_bucket()` is development convenience only; production buckets must pre-exist and be provisioned externally.
- PostgreSQL/pgvector remain a separate unverified runtime integration task.
- The broader Phase 02 gate remains open for live infrastructure verification, durable background jobs, CI and clean-checkout operational proof.
- No claims are made here about full tenant isolation or enterprise-grade security certification.

## Files

- `backend/sigillum/infrastructure/storage/__init__.py`
- `backend/sigillum/config.py`
- `backend/sigillum/application/services/review_service.py`
- `backend/sigillum/api/routes.py`
- `apps/api/main.py`
- `tests/unit/test_storage.py`
- `tests/integration/test_api.py`
