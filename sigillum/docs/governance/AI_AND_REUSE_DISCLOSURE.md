# AI, reuse and contribution disclosure register

**Status:** updated 2026-11-09. This document must be reviewed before submission and updated if dependencies, hosted services, assets or contributors change.

## Pre-window material (disclose separately; do not claim as event-window implementation)

The initial `INKLOOM_SIGILLUM_PHASE_00_STARTER.zip` and subsequent `INKLOOM_SIGILLUM_PHASE_00_01_PLANNING_PACK.zip` were prepared with ChatGPT assistance on 2026-11-08 before the participant confirmed that the official build window had started. They contain planning and design documents, a suggested folder scaffold, requirements and governance registers, an architecture plan, synthetic ORBITA brand-pack data, synthetic sample assets/fixtures and fixture-generation/evaluation helpers. They did **not** contain the functional API, implemented authentication and permissions, database models used by the MVP, content-processing/review workflow, deterministic adjudicator, decision/patch routes or completed Next.js application screens described in the later build activity log.

The planning files and ORBITA fixtures were carried forward into the event-window implementation. That reuse is disclosed here. The participant should retain the original archive and organiser's exact build-window announcement to support accurate provenance. If organisers disallow the reuse of pre-window generated assets or helpers, remove or recreate those items according to their instructions.

## Event-window AI assistance

After the participant stated on 2026-11-08 that the official build window had started, ChatGPT assisted with designing, generating, editing and debugging substantial portions of the API, database integration, authentication, content extraction, deterministic verification, review/decision flows, frontend source, tests and documentation. Build 009 also used ChatGPT assistance to add the storage abstraction, S3-compatible adapter, API integration, hash-verified downloads, tests and documentation. Build 010 used ChatGPT assistance to implement the SQLAlchemy engine factory, migration-driven local startup, migration/readiness diagnostics, a forward-only pgvector extension migration, PostgreSQL service-backed CI configuration, regression tests and documentation. Build 011 used ChatGPT assistance to add persisted tenant/brand/membership/session models, membership-based authorization, server-side session revocation, workspace context switching, role-gated member management, signed session-bound file grants, PostgreSQL RLS policies and verification, PostgreSQL CI hardening, migration backfill safety, frontend workspace selection/member management, regression tests and documentation. ChatGPT also helped interpret test failures, inspect migration edge cases and prepare local evaluation reports. This assistance must be disclosed as significant AI assistance; it must not be represented as code written unaided by the participant.

The participant is responsible for reviewing and understanding the code, checking licences, testing it on their own machine, modifying it as needed, making the final technical decisions and truthfully explaining their own contribution. The source and commit history should accurately reflect the actual development process. Do not fabricate commits, timestamps, authorship or test results.

## Material and provider register

| Material / service | Source | Use in current build | Licence / data-handling note | Disclosure |
|---|---|---|---|---|
| Phase 00/01 planning, requirements and design documents | ChatGPT-assisted, based on participant-supplied project/problem documents | Product/engineering plan | Not a third-party software package | Pre-window AI-assisted planning material; retained and disclosed |
| ORBITA synthetic Brand Knowledge Pack and fixture assets | ChatGPT-assisted synthetic content; fixture helper from starter | Demo and regression evaluation | Synthetic, not customer/third-party brand data | Pre-window generated assets/helpers reused; disclose and confirm organiser permission |
| Event-window Python API/application code | ChatGPT-assisted implementation and debugging | Backend MVP | Participant must review; dependencies have individual licences | Significant build-window AI assistance |
| Event-window frontend source | ChatGPT-assisted implementation and debugging | Next.js UI source | Dependency licences to be retained in lockfile after install | Significant build-window AI assistance; participant subsequently verified lint, typecheck and production build on Windows (2026-11-08) |
| FastAPI, Pydantic, SQLAlchemy, Alembic, pypdf, python-docx, Pillow, pytesseract, PyJWT and other Python dependencies | Open-source packages pinned in `pyproject.toml` | API, persistence, extraction, OCR and security | Review package licences and current versions before submission | Dependency list is disclosed in `pyproject.toml` |
| Next.js, React, TypeScript, Tailwind CSS and Lucide React | Open-source packages declared in `apps/web/package.json` | Frontend | Participant ran npm install and generated package-lock locally; retain and commit that exact lockfile. Resolved dependency versions and package licences should be reviewed before final submission | Dependency declarations disclosed; exact resolved versions not yet captured |
| Tesseract OCR | Local system package installed by participant | PNG/JPG OCR | Local processing; system package/licence version should be recorded on demo machine | No hosted OCR provider or external upload |
| boto3 (pinned in `pyproject.toml`) | Open-source Python SDK | Optional S3-compatible object-storage adapter; no external bucket was accessed during Build 009 tests | Apache-2.0; provider endpoint, egress, retention, encryption and backup remain operator responsibilities | Build 009; significant ChatGPT-assisted integration; offline fake-client tests only, not live MinIO/AWS verification |
| Hosted LLM / embeddings / external AI API | None used by current MVP | Not applicable | No confidential content sent to a hosted model by this application | Not used |
| PostgreSQL/pgvector | PostgreSQL engine path, Alembic migration and PostgreSQL RLS policies are implemented; a non-superuser CI service job is configured | SQLite is the local runtime used for Build 011 tests; hosted PostgreSQL job not yet observed passing | No live PostgreSQL verification in this authoring environment | Report as implemented but runtime verification pending; do not claim production isolation yet |
| MinIO / S3-compatible storage | Optional boto3 adapter and Compose scaffold | No live bucket or MinIO endpoint used | Not connected in this build session | Live MinIO/AWS verification remains pending |

## Current contribution statement (participant should personalise truthfully)

The participant is the sole project owner and is responsible for product direction, architecture decisions, integration, testing, validation, final changes, deployment and the final demonstration, to the extent those tasks they personally perform. ChatGPT provided significant coding, debugging, documentation and planning assistance as listed above. The participant should only claim implementation, testing, deployment or design tasks they have personally checked and can explain.

## Build 011 verification note

The Build 011 backend suite ran with **84 passed and 1 skipped** under SQLite. The skipped case is the PostgreSQL-only RLS enforcement test and is expected to run in CI against a non-superuser `NOBYPASSRLS` role. A copied Build 010 database upgraded to `20261109_0003`, and a synthetic multi-brand backfill fixture confirmed unassociated legacy accounts receive no automatic memberships. The Build 011 frontend could not be installed in the authoring environment because `npm ci` timed out; participant lint/typecheck/build checks must be rerun on the revised source. No new third-party runtime provider or Python dependency was introduced in Build 011.

## Update protocol

For each added dependency, model, dataset, API, template, generated asset or service, record its name/version, source, licence/terms, purpose, date introduced, data sent/retained, cost limit, fallback and AI involvement. Preserve dependency lockfiles, service settings and source references. Do not upload real confidential brand materials to third-party providers without the brand's permission and a verified data-handling basis.
