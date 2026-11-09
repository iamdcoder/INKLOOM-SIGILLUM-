# Inkloom Sigillum — Build 014 handoff

**Build:** 014  
**Baseline:** Build 013 (cumulative source snapshot; includes Builds 001–013)  
**Milestone:** Phase 04 — Brand Control Center and Knowledge Pack lifecycle  
**Phase status:** Partially implemented; not signed off  
**Date:** 2026-11-09

## What changed in Build 014

Build 014 adds controlled knowledge-source intake and strengthens approval/provenance boundaries.

1. **PDF/DOCX source ingestion.** Added an authenticated Brand Owner endpoint to validate a PDF/DOCX signature, apply the configured size limit, store the original under a tenant+brand+draft-scoped private object key, and add it as a non-authoritative draft source.
2. **Fail-closed ClamAV scanning.** Added a ClamAV TCP `INSTREAM` adapter. `CLEAN`, `INFECTED`, `UNAVAILABLE` and `ERROR` are distinct states. Scanner outage never becomes CLEAN. A source is parsed only after a CLEAN scan.
3. **Source extraction manifest.** Retains the original SHA-256, bounded extracted text, logical region metadata, parser confidence/status and warnings. Extracted text is capped at 20,000 characters and the manifest exposes at most 500 regions. The original binary remains private.
4. **Quarantine and recovery.** Download, extraction inspection and approval are blocked until the source is CLEAN and extraction is complete. Brand Owners can retry a scan after the scanner becomes available. A changed original hash fails closed.
5. **Asset scan enforcement.** Uploaded PNG/JPEG/WebP assets are also scanned. A non-CLEAN result blocks preview and approval; Brand Owners can retry scanning. A rescan that is no longer CLEAN suspends a draft asset's previous approval.
6. **Generic editor hardening.** The generic JSON editor cannot create approval provenance, inject upload metadata or alter uploaded-source extraction/hash fields. Editing an already-approved record downgrades it to draft so it must be explicitly approved again.
7. **Version comparison.** Added a scoped API and UI to compare immutable published versions at record/field level. Private object-store keys are redacted in comparison output; long values are bounded.
8. **Brand Control Center UX.** Added PDF/DOCX upload, scan-state display, retry scan, extracted-region inspection and download controls. The UI prevents approval of uploaded sources until scan and extraction gates pass.
9. **Operations.** Added optional ClamAV Docker Compose service and `.env.example` settings.
10. **Regression coverage.** Added ClamAV protocol/response tests; upload tests for scanner outage, clean retry, extraction, download and approval; infected-file quarantine tests; source provenance tampering tests; version-diff tests.

## Run ClamAV locally

The API's default configuration expects ClamAV on `127.0.0.1:3310`.

```powershell
docker compose --profile security up -d clamav
docker compose ps clamav
docker compose logs -f clamav
```

Allow the ClamAV container to finish its initial signature database update before expecting CLEAN results. If the API itself runs inside the same Compose network, set `CLAMAV_HOST=clamav`; when the API runs directly on the host, keep `CLAMAV_HOST=127.0.0.1`.

Relevant `.env` settings:

```dotenv
CLAMAV_HOST=127.0.0.1
CLAMAV_PORT=3310
CLAMAV_TIMEOUT_SECONDS=30
```

**Security behaviour:** when ClamAV is offline, uploaded source documents and assets remain quarantined. Do not bypass the scan gate or mark a file CLEAN manually. The standard submission intake pipeline is still tracked separately under Phase 05 and is not represented as malware-scanned by this change.

## Verification performed

- Backend suite: run `pytest -q`; the final run passed (see `reports/BUILD_014_TEST_RESULTS.txt` for the recorded command/result).
- Python compilation: `python -m compileall -q backend apps migrations tests scripts` — passed.
- Alembic: local SQLite database current at `20261109_0004` — passed.
- Database verifier: all 16 required tables present; RLS is not applicable to SQLite.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** across 12 synthetic cases. This is a deterministic regression set, not a general accuracy claim.
- ClamAV unit protocol tests use a fake TCP socket. No live ClamAV daemon was available in this environment; Docker scanner runtime remains unverified.
- Next.js TSX parser check passed for `apps/web/app/brand/page.tsx`.
- Full `npm ci`, lint, typecheck and production build were **not completed**. Dependency installation timed out and the required local `node_modules` binaries were unavailable. Do not treat frontend production build as verified.
- Live PostgreSQL RLS/row-lock behaviour and live MinIO/AWS storage remain unverified.

## Still open before Phase 04 sign-off

- Live non-superuser PostgreSQL RLS and concurrent-publication CI.
- Owner-configurable asset usage, dimensions, palette, clear-space, scope and validity policy enforcement.
- Fully guided create/edit forms for all fact, policy, terminology and voice fields; current JSON editor remains an expert editing surface.
- Further normalized schema and conflict coverage for all source/asset/voice/term scope combinations.
- Browser walkthrough/screenshots after dependencies are available and Next.js lint/typecheck/build pass.
- Operational cleanup for quarantined-object retention/deletion and a live malware-signature update/recovery run.

See `docs/phase-gates/PHASE-04-STATUS.md` and `docs/technical/BUILD_014_PHASE04_SOURCE_INTAKE.md`.

## Apply Build 014

1. Back up the repository, `.env`, `data/` and database.
2. Extract `Sigillum_Build_014.zip` over the project root. Preserve `.env`, `.git`, `data/`, `.venv/` and `apps/web/node_modules/`; these are excluded from the archive.
3. Activate the existing virtual environment and install no new Python package for this increment; the malware adapter uses the Python standard library.
4. Start ClamAV as described above. Keep the scanner unavailable only when you deliberately want to test quarantine behaviour.
5. Run the checks below.

```powershell
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python scripts/verify_database.py
pytest -q
python scripts/evaluate_golden_cases.py
python -m compileall -q backend apps migrations tests scripts
```

From `apps/web`, once dependencies are available:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```

Build 014 adds no database migration; the expected head remains `20261109_0004`.

## Integrity and scope

The archive is a cumulative source snapshot. It excludes `.git`, `.env` files, local databases, private uploaded originals, virtual environments, `node_modules`, build caches and Python bytecode.

**Definition of done for this increment:** controlled PDF/DOCX knowledge-source intake, fail-closed scanning, source extraction/download gating, asset scanning gates, generic-editor provenance protection and immutable version diffs are implemented and backend-regression tested. **Definition of done for Phase 04 is not met yet.**
