# Inkloom Sigillum

**Evidence-first brand assurance. Brand truth, verified before it ships.**

Sigillum is a pre-publication review workspace for checking text and static creative assets against an approved, scoped and time-aware Brand Knowledge Pack. It produces a source-linked finding ledger, exposes uncertainty, suggests constrained corrections and leaves final approval with an authorised human.

> **Build-window integrity:** this repository contains disclosed AI-assisted planning/scaffolding and synthetic fixture material prepared before the participant confirmed the official build window had opened, plus application code and tests developed after that confirmation. See `docs/governance/AI_AND_REUSE_DISCLOSURE.md`, `docs/governance/BUILD_WINDOW_LOG.csv` and `docs/governance/BUILD_ACTIVITY_LOG.csv`. The participant must verify the event's official start/end and submission cutoff, review and understand the code, and make accurate contribution disclosures.

## Current implementation status

The current MVP has a real, locally runnable API and an implemented Next.js UI source tree. The API/integration suite has **27 passing tests** in the recorded development environment. The synthetic golden evaluation reports **11 automated PASS, 1 MANUAL_REVIEW_REQUIRED and 0 FAIL**. These are test outcomes for the included cases only, not a general accuracy estimate or external certification.

### Implemented in this MVP

- Demo authentication for creator, reviewer, brand owner and administrator roles.
- Creator-owned submission access checks; reviewer/owner/admin review access within one synthetic demo workspace.
- PDF, DOCX, TXT, PNG and JPG/JPEG intake with byte limits, signature/type checks and defensive parsing limits.
- Text extraction from TXT, searchable PDF, DOCX paragraphs/tables; local Tesseract OCR for PNG/JPG with word boxes and extraction confidence.
- Immutable source versions with SHA-256 content hashes and retained original files.
- Deterministic savings-claim checks against configured approved facts, required scope fields, authority, and publication validity dates.
- Conservative configured terminology, tone-pattern and untrusted-instruction-text checks.
- A canonical finding ledger with distinct verdict, severity, confidence, extraction confidence, evidence sufficiency, reason code, source references, exact text span or explicit manual-review state.
- Hash-bound TXT correction proposals that create a new content version and trigger a new review; revised PDFs, DOCX and images can be re-uploaded as new immutable versions.
- Human reviewer decisions, mandatory reasons for reject/request-changes/override, role-gated override, approval blocking for unresolved blocking/review-required findings, and audit events.
- Explicit visual review findings for logo identity and contrast on images, and for embedded visual content in PDF/DOCX.
- Next.js screens for login, overview, submissions/upload, review workbench, Brand Control Center snapshot and audit history.

### Not implemented or not yet verified

- The current runtime is a **single synthetic demo workspace**. PostgreSQL row-level security, production multi-tenant isolation, enterprise identity, invitations and SSO are not implemented.
- SQLite and private local filesystem storage are the default active adapters. `infra/docker-compose.yml` is a PostgreSQL/pgvector + MinIO scaffold; the current API does not yet use those services.
- Reviews execute synchronously in the API process. The worker directory is a scaffold; durable leases, retry budgets, LangGraph checkpointing, resumable jobs and SSE progress are not active.
- Retrieval is a static, local Brand Knowledge Pack lookup for supported deterministic rules. Hybrid lexical/vector retrieval, RRF and permission-aware pgvector search are not implemented.
- Claim extraction is deliberately narrow (configured numeric savings patterns and selected quantified statements). It is not a general semantic claim verifier or legal compliance engine.
- PNG/JPG OCR is local Tesseract. Scanned-PDF OCR and embedded-image OCR within PDF/DOCX are not implemented.
- Logo identity matching, pixel-level palette analysis and standards-grade contrast measurement are not automated; the reviewer must inspect the original and record a reason.
- Tone checks are configured phrase/pattern checks, not a calibrated model of brand voice.
- Text patching is supported for TXT. Other formats require editing in their native application and uploading a new version.
- A full standalone Correction Studio, Reviewer Console, Governance/Impact Radar and Administration configuration UI are not complete.
- The participant's Windows environment has now passed `npm run lint`, `npm run typecheck` and `npm run build` (2026-11-08). The generated `apps/web/package-lock.json` should be committed and retained with the submission.
- No hosted LLM, embedding, OCR or external data provider is called by this build.

## Stack

| Layer | Current MVP | Not to be confused with |
|---|---|---|
| Web | Next.js App Router, React, TypeScript, Lucide, custom CSS tokens | Participant-verified local build; not a production deployment or comprehensive browser E2E suite |
| API | FastAPI, Pydantic | Independent microservices |
| Persistence | SQLAlchemy 2.x, local SQLite, Alembic initial migration | Active PostgreSQL/pgvector runtime |
| File storage | Private local filesystem, SHA-256 metadata | Active S3/MinIO integration |
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

## Tests and evaluation

From the repository root with the Python environment active:

```powershell
pytest
python scripts/evaluate_golden_cases.py
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
    knowledge/         Synthetic Brand Knowledge Pack reader
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

- Backend test suite: **27 passed** in the recorded local run.
- Synthetic golden corpus: **11 automated PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL** across 12 cases. The manual case is intentional: logo identity and contrast are not auto-certified.
- Each review now stores the full Brand Knowledge Pack snapshot, its SHA-256 fingerprint and the deterministic ruleset version. The API exposes a version-history timeline with hashes and decisions.
- Participant Windows frontend verification: **lint passed, TypeScript passed, production build passed** on 2026-11-08. Keep the participant-generated `apps/web/package-lock.json` in the submission repository.
- Live API vertical-slice smoke: **8 checks passed** against a clean local database: readiness, authentication, upload, evidence-linked contradiction, approval blocking, hash-bound correction, immutable version history, corrected-version approval and audit events. See `docs/technical/LIVE_VERTICAL_SLICE_SMOKE.md`.

See `docs/phase-gates/PHASE-02-STATUS.md` for the remaining gate items and exact commands.


## Build 006 — Visual Evidence Intelligence

Build 006 adds source-mapped logical text regions and a first image-region inspection path. PNG/JPG extraction now stores image dimensions, EXIF orientation, decoded-pixel fingerprint, descriptive dominant-colour samples, line-level OCR regions, polygon geometry, normalized bounding boxes, word boxes, coordinate-system metadata, Tesseract engine/version, a bounded OCR timeout and OCR confidence. The Review Workbench overlays the OCR polygons on the preserved original image and links selectable regions to related findings.

For social/print submissions, an approved in-scope Brand Knowledge Pack policy can provide a structured minimum contrast ratio. Sigillum performs a conservative local pixel estimate around an OCR line and records `PASS`, `FAIL` or `UNMEASURABLE` with sampled colours, method and limitations. A measured failure or an in-scope unmeasurable region routes to human review; it never automatically blocks or approves on its own. Palette output is descriptive only. Logo identity remains manual confirmation.

TXT lines and DOCX paragraphs/table rows now retain logical character offsets. PDFs retain page dimensions and page text offsets, but this build does not claim rendered PDF text polygons or scanned-PDF OCR. These remaining items are tracked in `docs/phase-gates/PHASE-06-STATUS.md`.
