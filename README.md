# Inkloom Sigillum

**Evidence-first brand assurance. Brand truth, verified before it ships.**

Sigillum is a pre-publication review workspace for checking text and static creative assets against an approved, scoped and time-aware Brand Knowledge Pack. It produces a source-linked finding ledger, exposes uncertainty, suggests constrained corrections and leaves final approval with an authorised human.

> **Build-window integrity:** this repository contains disclosed AI-assisted planning/scaffolding and synthetic fixture material prepared before the participant confirmed the official build window had opened, plus application code and tests developed after that confirmation. See `docs/governance/AI_AND_REUSE_DISCLOSURE.md`, `docs/governance/BUILD_WINDOW_LOG.csv` and `docs/governance/BUILD_ACTIVITY_LOG.csv`. The participant must verify the event's official start/end and submission cutoff, review and understand the code, and make accurate contribution disclosures.

## Current implementation status

The MVP has a locally runnable API and Next.js application source. Build 009 added private local/S3-compatible object storage and SHA-256-verified originals. Build 010 made Alembic the development schema lifecycle and added PostgreSQL 17 + pgvector CI. Build 011 added persisted tenant/brand memberships, revocable server sessions, multi-workspace selection/switching, role-gated membership management, short-lived session-bound file grants and PostgreSQL RLS policies. Build 012 introduced tenant+brand Knowledge Pack isolation, source registry, per-record owner decisions and private raster asset upload/integrity checks. Build 013 moved Knowledge Pack heads, immutable snapshots, drafts and record-decision history into transactional database tables, with stale-write protection and legacy filesystem import. **Build 015** adds owner-configurable asset usage policies for allowed channels and declared uses, minimum dimensions, measured palette tolerance, validity windows and manual clear-space review. It persists submission intended-use metadata and applies asset restrictions during review only when the uploaded image bytes have an exact SHA-256 match to an approved catalogue asset. This is not logo recognition inside a different flattened creative. The current backend suite has **119 passed, 1 skipped, 0 failed (120 collected)** in SQLite mode; the skipped test is the PostgreSQL-only RLS enforcement test. The synthetic golden evaluation remains **11 automated PASS, 1 MANUAL_REVIEW_REQUIRED and 0 FAIL**. These are deterministic regression results, not a general accuracy estimate or external certification. Live ClamAV, PostgreSQL RLS/concurrency, and full frontend lint/typecheck/build remain pending.

### Implemented in this MVP

- Password-based demo authentication with PBKDF2 password hashing and server-side revocable JWT sessions. JWT role/tenant claims are informational; each API request re-reads the active membership and derives authority from the database.
- Persisted tenants, brands, per-brand memberships and user sessions. A user with multiple active memberships must explicitly select a workspace/brand at login and can switch context from the sidebar; switching revokes the previous session.
- Creator and agency contributors are restricted to their own submissions. Reviewers, brand owners and administrators receive only the access allowed by their selected brand membership. Brand owners can add creator/agency/reviewer memberships; administrators can manage roles and activation. The last active administrator is protected from demotion/deactivation.
- Five-minute (configurable 1–15 minute) signed original-file grants are bound to the user, session, membership, tenant, brand and content version. Revoked sessions or inactive memberships invalidate outstanding grants.
- PDF, DOCX, TXT, PNG and JPG/JPEG intake with byte limits, signature/type checks and defensive parsing limits.
- Text extraction from TXT, searchable PDF, DOCX paragraphs/tables; local Tesseract OCR for PNG/JPG with word boxes and extraction confidence.
- Immutable source versions with SHA-256 content hashes and retained original files.
- A storage port with atomic/private local filesystem storage and an opt-in boto3 S3-compatible adapter (MinIO/AWS-style API); authenticated downloads are read through the API and re-hash the stored bytes before returning them.
- Readiness reports the actual storage driver and fails closed when the configured storage service is unavailable; local mode also probes filesystem write access. Storage outages are distinct from parser failures and never produce an approval state.
- Deterministic savings-claim checks against configured approved facts, required scope fields, source precedence, publication valid time and review record time.
- Approved-only, scoped lexical + structured RRF evidence candidate retrieval with explainable ranks and temporal eligibility; vector/pgvector retrieval is explicitly not configured.
- Conservative configured terminology, tone-pattern and untrusted-instruction-text checks.
- A canonical finding ledger with distinct verdict, severity, confidence, extraction confidence, evidence sufficiency, reason code, source references, exact text span or explicit manual-review state.
- Hash-bound TXT correction proposals that create a new content version and trigger a new review; revised PDFs, DOCX and images can be re-uploaded as new immutable versions.
- Human reviewer decisions, mandatory reasons for reject/request-changes/override, role-gated override, approval blocking for unresolved blocking/review-required findings, and audit events.
- Explicit visual review findings for logo identity and contrast on images, and for embedded visual content in PDF/DOCX.
- Next.js screens for login, overview, submissions/upload, review workbench, owner-governed Brand Control Center, Knowledge Pack version history, audit history and a role-gated Workspace Access screen. The sidebar includes a working workspace/brand context selector for users with multiple memberships.
- Tenant+brand-scoped Knowledge Pack draft/edit/validate/publish lifecycle with database-backed active heads, immutable JSON snapshots, drafts and append-only record-decision history. Build 013 adds optimistic draft compare-and-swap, row-locked/revision-checked publication, a scoped decision-history endpoint and automatic import of eligible Build 012 filesystem drafts. Build 014 adds PDF/DOCX source-document intake, private hash-bound storage, fail-closed ClamAV scanning, bounded extraction manifests, scan retry, gated source download/approval, brand asset scan gating, generic-editor provenance protection and immutable version diff. Build 015 adds owner-authored `assets.usage_policies` with channel/use restrictions, dimension limits, palette tolerance and validity windows, along with a declared submission intended-use field. Palette comparison is a bounded RGB-distance estimate, not brand identity or colour-management certification. Clear-space rules remain human-reviewed. Exact asset use restrictions apply only to byte-identical approved uploads, not logos detected within another image. A new non-demo brand starts with an empty pack rather than inheriting ORBITA facts/assets. Local JSON files remain compatibility mirrors; binary files remain in private storage. Each review preserves the exact pack snapshot/fingerprint used.

### Not implemented or not yet verified

- The default seeded runtime remains one synthetic ORBITA workspace/brand, while Build 011/012 support persisted multi-membership contexts and tenant+brand Knowledge Pack path isolation. Build 011 installs PostgreSQL RLS policies with `ENABLE` and `FORCE` on tenants, brands, memberships, sessions, submissions, content versions, reviews, findings, patches, decisions and audit events. However, live PostgreSQL execution is unavailable in this authoring environment; the non-superuser PostgreSQL CI run must pass before production multi-tenant isolation is considered verified. Enterprise identity/SSO, account invitation and account creation flows are not implemented. Workspace Access currently links existing accounts.
- SQLite and private local filesystem storage remain the default local configuration. Development startup applies Alembic migrations; readiness verifies the schema head. PostgreSQL URLs use the pinned psycopg 3 driver and bounded connection pooling. The PostgreSQL service job uses a non-superuser `NOBYPASSRLS` application role and `scripts/verify_database.py` now checks that every protected table has RLS enabled, forced and covered by a policy. Its hosted result must still be observed passing after push; no live PostgreSQL service was available locally.
- Reviews execute synchronously in the API process. The worker directory is a scaffold; durable leases, retry budgets, LangGraph checkpointing, resumable jobs and SSE progress are not active.
- Retrieval uses a local deterministic lexical + structured RRF baseline for supported facts. Vector/pgvector search, HNSW indexing, retrieval Recall@5/MRR benchmarks and database-backed permission-aware search are not implemented.
- Claim extraction is deliberately narrow (configured numeric savings patterns and selected quantified statements). It is not a general semantic claim verifier or legal compliance engine.
- PNG/JPG OCR is local Tesseract. Scanned-PDF OCR and embedded-image OCR within PDF/DOCX are not implemented.
- Logo identity matching, pixel-level palette analysis and standards-grade contrast measurement are not automated; the reviewer must inspect the original and record a reason.
- Tone checks are configured phrase/pattern checks, not a calibrated model of brand voice.
- Text patching is supported for TXT. Other formats require editing in their native application and uploading a new version.
- A full standalone Correction Studio, Reviewer Console, Governance/Impact Radar and Administration configuration UI are not complete.
- Knowledge Pack editing still uses a structured JSON expert editor rather than complete guided create/edit forms for every fact, policy, terminology and voice field. PNG/JPEG/WebP asset upload uses fail-closed ClamAV scanning in Build 014; PDF/DOCX Knowledge Pack source uploads are also scanned before parsing. The ordinary submission upload pipeline is not yet claimed as malware-scanned. Build 015 implements owner-defined asset usage rules for channels, declared uses, minimum dimensions, palette thresholds and validity. Clear-space remains a manual-review requirement; logo recognition inside arbitrary flattened creatives is not implemented. Automatic impact re-review after a pack publication is not implemented.
- Build 013 makes the database authoritative for Knowledge Pack metadata, immutable snapshots, drafts, decisions and the active pointer. The `data/brand_packs/` JSON snapshot/pointer files are compatibility mirrors; uploaded asset bytes stay in the private storage adapter. PostgreSQL RLS and row-lock/concurrent-publication behaviour are implemented in the migration/code but not runtime-verified until the hosted non-superuser PostgreSQL CI job passes.
- The participant verified `npm run lint`, `npm run typecheck` and `npm run build` on the pre-Build-011 frontend on Windows (2026-11-08). Builds 011/012 changed login/workspace context and Brand Control Center UI; Build 014 adds Knowledge Pack source intake, scan/retry, extraction/download gates and version comparison UI. In this authoring environment, a TypeScript compiler API parse check of `apps/web/app/brand/page.tsx` passed, but `npm ci` timed out; full lint/typecheck/production build are not verified for the cumulative Build 014 source. Rerun those checks locally and retain `apps/web/package-lock.json`.
- No hosted LLM, embedding, OCR or external data provider is called by this build.

## Stack

| Layer | Current MVP | Not to be confused with |
|---|---|---|
| Web | Next.js App Router, React, TypeScript, Lucide, custom CSS tokens | Participant-verified local build; not a production deployment or comprehensive browser E2E suite |
| API | FastAPI, Pydantic | Independent microservices |
| Persistence | SQLAlchemy 2.x, SQLite local default, PostgreSQL + psycopg 3 engine path, Alembic migration chain | Live PostgreSQL service run is pending CI; pgvector extension migration is in place |
| File storage | Private local filesystem by default; opt-in S3-compatible adapter; SHA-256 re-check on download | Live MinIO/AWS endpoint not verified in this build environment |
| Extraction | pypdf, python-docx, Pillow, pytesseract/Tesseract | Full multimodal document understanding |
| Verification | Pure deterministic Python checks | LLM truth adjudication |
| Tests | pytest unit/integration + synthetic golden evaluator | Independent external validation |

## Requirements

- Python 3.11+ (Python 3.13 recommended)
- Node.js 20.9+ (Node 22 recommended) and npm
- Tesseract OCR installed and available on `PATH` for PNG/JPG OCR
- Windows PowerShell, macOS or Linux

## Run locally — Windows PowerShell

Open PowerShell in the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force data | Out-Null
python -m alembic upgrade head
python scripts/verify_database.py
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: <http://127.0.0.1:8000/docs>  
Liveness: <http://127.0.0.1:8000/health/live>  
Readiness: <http://127.0.0.1:8000/health/ready>

The development API seeds four demo accounts on first startup. Their shared password is read from `SIGILLUM_DEMO_PASSWORD` in `.env` and defaults to `ChangeMe-Local-Only` for local use only.

| Role | Email |
|---|---|
| Creator | `creator@orbita.demo` |
| Reviewer | `reviewer@orbita.demo` |
| Brand Owner | `owner@orbita.demo` |
| Administrator | `admin@orbita.demo` |

**Never use these accounts or the default password for a public deployment or real confidential material.** Change all secrets and passwords before sharing a running instance. The local demo is not a production security configuration.

## Run the web app

In a second terminal:

```powershell
cd apps\web
if (!(Test-Path .env.local)) { Copy-Item .env.local.example .env.local }
npm install
npm run dev
```

Open <http://localhost:3000>. The API URL defaults to `http://127.0.0.1:8000/api/v1`; configure `NEXT_PUBLIC_API_URL` in `apps/web/.env.local` if needed.

Build verification:

```powershell
npm run build
```

The participant has already confirmed a successful production build on the Windows development machine (2026-11-08). Re-run this command on the final submission checkout after the last source change.

## PostgreSQL + pgvector development database

The default local walkthrough uses SQLite. To exercise the PostgreSQL/pgvector path, start the development-only backing services from the repository root:

```powershell
docker compose -f infra/docker-compose.yml --profile infra up -d db
```

Set `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env` to use the same local-only password (the example `.env` already provides a development-only value). For example:

```dotenv
DATABASE_URL=postgresql+psycopg://sigillum:YOUR_LOCAL_PASSWORD@127.0.0.1:5432/sigillum
```

The Compose service reads `POSTGRES_PASSWORD`; set the same value in `.env` before starting it. Then run:

```powershell
python -m alembic upgrade head
python scripts/verify_database.py
```

A forward-only Alembic migration installs the `vector` extension when the target is PostgreSQL; the original initial migration remains unchanged. The API's development startup also applies migrations automatically; production does not auto-migrate and must run the migration command as a deployment step. Do not use the sample local password or publish the database port on an untrusted network.

## Optional S3-compatible object storage

The local default remains private filesystem storage. To use MinIO or another S3-compatible endpoint, start the object store, create a private bucket, then set these values in `.env`:

```dotenv
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=http://127.0.0.1:9000
S3_BUCKET=sigillum-private
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=sigillum
S3_SECRET_ACCESS_KEY=replace-with-a-local-secret
S3_VERIFY_SSL=true
```

For a local MinIO development instance, provision the bucket using the MinIO Client (`mc`) or the provider console before starting the API. Development startup can create a missing bucket when access is permitted; production must provision its bucket and credentials outside the application. Do not expose the MinIO console or API publicly with sample local credentials. The S3-compatible adapter is covered by offline adapter tests; a live MinIO deployment test is still required before describing that external service as production-verified.

Original files are served only through the authenticated API route. The route recomputes SHA-256 before returning bytes. The adapter does not generate public object URLs or expose storage credentials to the browser.

## Knowledge Pack malware scanning (Build 014)

Brand Owner uploads of Knowledge Pack PDF/DOCX sources and raster brand assets use the ClamAV TCP `INSTREAM` protocol. Start the optional local scanner with:

```powershell
docker compose --profile security up -d clamav
docker compose ps clamav
docker compose logs -f clamav
```

The default API settings are `CLAMAV_HOST=127.0.0.1`, `CLAMAV_PORT=3310` and `CLAMAV_TIMEOUT_SECONDS=30`. If the API runs in the same Compose network, set `CLAMAV_HOST=clamav`. Let the scanner finish its initial signature database update. A scanner outage, timeout or invalid response is never interpreted as CLEAN: the upload remains quarantined and cannot be parsed (for source documents), downloaded, previewed or approved until a clean retry. Do not manually bypass this gate.

This Build 014 scanner path covers Brand Knowledge source documents and brand assets only; the regular creator submission pipeline remains a Phase 05 security gap. See `docs/technical/BUILD_014_PHASE04_SOURCE_INTAKE.md`.

## Tests and evaluation

From the repository root with the Python environment active:

```powershell
pytest
python scripts/evaluate_golden_cases.py
python scripts/verify_database.py
# With the API running in another terminal:
python scripts/smoke_vertical_slice.py
python -m compileall -q backend apps tests scripts
```

The golden report is written to `reports/golden_evaluation_latest.json`. The current synthetic set is designed to exercise the anchor 40%-versus-28% claim, a supported exact claim, expired/future facts, conflicting sources, missing evidence, unsupported quantified statements, instruction-like text, terminology, tone, low OCR confidence and visual manual review. The live smoke script then exercises the full creator-to-reviewer API path.

## Primary judge demo

See `docs/demo/DEMO_RUNBOOK.md`. The strongest flow is:

1. Log in as creator and upload `fixtures/documents/claim_40_percent.txt` with `direct_web`, `IN`, `en-IN`, `consumer`, `OFFER-ORBITA-OCT-NOV-2026` and a publication date in the approved validity window.
2. Inspect the `CONTRADICTED` claim, exact content span, approved 28% evidence and scope/validity metadata.
3. Apply the constrained TXT patch. Confirm version 2 has a different SHA-256 and a new review run.
4. Sign in as reviewer. Inspect all remaining findings and record a reason for each manual review item.
5. Approve only the latest exact content version. Show the bound hash and audit trail.
6. Upload `fixtures/images/social_supported_clean.png` to demonstrate OCR and the explicit human visual/contrast gates.

## Product invariants

1. No applicable approved proof means `UNVERIFIABLE`, not `SUPPORTED`.
2. Truth is scoped by offer, geography, channel, locale, audience and intended publication time.
3. Analysis proposes; deterministic policy code adjudicates configured rules; authorised humans decide.
4. Approval binds to the exact content hash and review context.
5. A content edit creates a new immutable version; historical versions and reviews remain inspectable.
6. Parse failure and low-confidence OCR never imply approval.
7. Uploaded content is untrusted data, never an instruction to execute tools or change permissions.
8. An honest manual-review state is preferable to pretending a visual check was performed.

## Repository map

```text
apps/
  api/                 FastAPI application entrypoint
  web/                 Next.js App Router experience
  worker/              Worker entrypoint scaffold (not active)
backend/sigillum/
  api/                 Routers, dependencies and request/response schemas
  application/         Review orchestration service
  domain/              Domain enums and boundaries
  infrastructure/      SQLAlchemy, security and storage boundary
  modules/
    content/           Safe file extraction and OCR
    knowledge/         Brand Knowledge Pack reader, immutable version store and draft lifecycle
    verification/      Deterministic claim/terminology/tone checks
    identity/          Identity module boundary (future expansion)
    retrieval/         Retrieval module boundary (future expansion)
    workflow/          Durable workflow module boundary (future expansion)
    correction/        Correction module boundary (future expansion)
    governance/        Governance module boundary (future expansion)
fixtures/              ORBITA pack, document/image fixtures and golden cases
docs/                  Product, UX, technical, governance, runbook and phase-gate records
migrations/            Alembic migration history
infra/                 Compose scaffold for Postgres/pgvector and MinIO
packages/contracts/    Shared API contract boundary (future generated client)
reports/               Reproducible evaluation output
scripts/               Startup, test, fixture and evaluation scripts
tests/                 Unit and integration suite
```

## Event contribution and provenance

Review `docs/governance/AI_AND_REUSE_DISCLOSURE.md` before submission. The supplied problem statement requires a functional product/MVP, judge-accessible source, demo/deployment, architecture and technology disclosures, reasonable testing evidence and accurate personal contribution. It also requires disclosure of reused code/assets/templates, external services and significant AI assistance. The repository keeps a record rather than claiming that planning/scaffold files were created during the official build window.

## Latest engineering verification

- Backend test suite: **119 passed, 1 skipped, 0 failed** in Build 015 (120 collected; SQLite/local unit + integration suite); the skip is the explicit PostgreSQL-only RLS test.
- Synthetic golden corpus: **11 automated PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL** across 12 cases. The manual case is intentional: logo identity and contrast are not auto-certified.
- Each review stores the full Brand Knowledge Pack snapshot, SHA-256 fingerprint and deterministic analysis-rule version. Build 008 added temporal truth and lexical + structured RRF provenance. Build 009 added private object storage and hash-verified original downloads. Build 010 made startup migration-driven. Build 011 added tenant/brand memberships, revocable sessions, access checks, workspace switching, member management, session-bound file grants and PostgreSQL RLS policies. Build 012 introduced tenant+brand Knowledge Pack isolation, source registry, per-record owner decisions, private raster asset upload/preview and SHA-256 integrity. Build 013 adds the transactional pack catalogue/drafts/decision ledger, optimistic draft writes, row-locked/revision-checked publication, Build 012 filesystem draft import and the decision-history API. Build 014 adds ClamAV-gated PDF/DOCX source intake, extraction/download/approval gates, asset scanning, editor provenance controls and published-version diff. Build 015 adds scoped asset use policies, declared submission intended use, deterministic exact-hash asset-use enforcement, palette measurement and clear-space manual review. PostgreSQL RLS/concurrency and live ClamAV runtime verification remain pending.
- Participant Windows frontend verification: **lint/typecheck/build passed on 2026-11-08 before Build 011**. Build 011/012/014/015 frontend changes still require full `npm run lint`, `npm run typecheck` and `npm run build`. A TypeScript compiler API syntax parse passed for the four TS/TSX files changed by Build 015, but `npm ci` timed out in the authoring environment and project-local binaries were unavailable. Keep the existing `apps/web/package-lock.json`.
- Live API vertical-slice smoke from Build 009: **9 checks passed** against a clean local database: readiness, authentication, upload, evidence-linked contradiction, approval blocking, hash-bound correction, immutable version history, corrected-version approval and audit events. See `docs/technical/LIVE_VERTICAL_SLICE_SMOKE.md`.

See `docs/phase-gates/PHASE-02-STATUS.md`, `PHASE-03-STATUS.md`, `PHASE-04-STATUS.md`, `PHASE-07-STATUS.md` and `PHASE-08-STATUS.md` for remaining gate items and exact commands.


## Build 015 — Owner-configurable asset usage policy

Build 015 adds per-asset-kind policy configuration to the Brand Control Center draft. A Brand Owner can set allowed brand channels, allowed declared uses, minimum width/height, an approved hex palette, RGB-distance tolerance, minimum measured palette coverage, validity dates and severity. These settings remain draft-only until the owner validates and publishes the containing Knowledge Pack version.

A bounded palette is extracted from newly uploaded raster brand assets and retained in the asset manifest. Validation compares measured colours using weighted RGB distance. This is a rough deterministic guardrail, not perceptual colour difference, ICC-aware colour management, visual brand-fit evaluation or logo identity certification. If a palette rule exists but a legacy asset has no measured palette, validation returns `ASSET_PALETTE_UNMEASURABLE` and does not misrepresent missing data as a measured 0% match. Clear-space ratio is recorded as a manual-review requirement.

Submissions now include a controlled declared `intended_use` value, persisted with the submission and included in review context. Review-time channel/use/validity rules only apply when the uploaded image bytes have an exact SHA-256 match to an approved catalogue asset. The implementation does not discover a logo embedded inside a different flattened creative, nor does it use perceptual similarity as a decisive match.

Alembic revision `20261109_0005` adds `submissions.intended_use` with a backwards-compatible `general` default. It handles both existing Build 014 SQLite schemas and fresh schema creation where SQLAlchemy metadata has already created the column.

Backend verification: **119 passed, 1 skipped, 0 failed (120 collected)**. The skipped test requires live PostgreSQL RLS. SQLite is current at `20261109_0005`, all 16 required tables are present, `compileall` passes, and the deterministic synthetic golden evaluation remains **11 PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL**. The four modified TS/TSX files pass a TypeScript parser check; `npm ci` timed out and lint/typecheck/production build are not verified. Phase 04 remains open; see `docs/phase-gates/PHASE-04-STATUS.md` and `docs/technical/BUILD_015_ASSET_USAGE_POLICIES.md`.

## Build 014 — Knowledge Pack source intake and scan governance

Build 014 adds controlled PDF/DOCX upload as non-authoritative Knowledge Pack source records. Originals are stored privately under the active tenant/brand/draft namespace and bound to an original SHA-256. ClamAV `INSTREAM` scanning is fail-closed: only a CLEAN source proceeds to extraction, and a source cannot be downloaded, inspected or approved before scan success. Extracted source text is capped at 20,000 characters and the manifest returns at most 500 logical regions with parser status, confidence and warnings.

Uploaded PNG/JPEG/WebP brand assets use the same scan-status gate. Brand Owners can retry scans after scanner recovery. Generic JSON editing cannot inject approval or uploaded-source provenance fields; editing an already-approved record forces a return to draft. The published-version comparison view reports bounded record/field changes and redacts private object-storage references.

Backend verification: **108 passed, 1 skipped, 0 failed**; the skipped check requires a real PostgreSQL RLS environment. Golden evaluation: **11 PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL**. A source-file unit/integration harness tests the scanner protocol and quarantine paths; a live ClamAV runtime was not available. The frontend TSX parser check passed, but npm dependency installation timed out and full lint/typecheck/build remain unverified. Phase 04 remains open; see `docs/phase-gates/PHASE-04-STATUS.md` and `docs/technical/BUILD_014_PHASE04_SOURCE_INTAKE.md`.

## Build 006 — Visual Evidence Intelligence

Build 006 adds source-mapped logical text regions and a first image-region inspection path. PNG/JPG extraction now stores image dimensions, EXIF orientation, decoded-pixel fingerprint, descriptive dominant-colour samples, line-level OCR regions, polygon geometry, normalized bounding boxes, word boxes, coordinate-system metadata, Tesseract engine/version, a bounded OCR timeout and OCR confidence. The Review Workbench overlays the OCR polygons on the preserved original image and links selectable regions to related findings.

For social/print submissions, an approved in-scope Brand Knowledge Pack policy can provide a structured minimum contrast ratio. Sigillum performs a conservative local pixel estimate around an OCR line and records `PASS`, `FAIL` or `UNMEASURABLE` with sampled colours, method and limitations. A measured failure or an in-scope unmeasurable region routes to human review; it never automatically blocks or approves on its own. Palette output is descriptive only. Logo identity remains manual confirmation.

TXT lines and DOCX paragraphs/table rows now retain logical character offsets. PDFs retain page dimensions and page text offsets, but this build does not claim rendered PDF text polygons or scanned-PDF OCR. These remaining items are tracked in `docs/phase-gates/PHASE-06-STATUS.md`.
