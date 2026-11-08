# AI, reuse and contribution disclosure register

**Status:** updated 2026-11-08. This document must be reviewed before submission and updated if dependencies, hosted services, assets or contributors change.

## Pre-window material (disclose separately; do not claim as event-window implementation)

The initial `INKLOOM_SIGILLUM_PHASE_00_STARTER.zip` and subsequent `INKLOOM_SIGILLUM_PHASE_00_01_PLANNING_PACK.zip` were prepared with ChatGPT assistance on 2026-11-08 before the participant confirmed that the official build window had started. They contain planning and design documents, a suggested folder scaffold, requirements and governance registers, an architecture plan, synthetic ORBITA brand-pack data, synthetic sample assets/fixtures and fixture-generation/evaluation helpers. They did **not** contain the functional API, implemented authentication and permissions, database models used by the MVP, content-processing/review workflow, deterministic adjudicator, decision/patch routes or completed Next.js application screens described in the later build activity log.

The planning files and ORBITA fixtures were carried forward into the event-window implementation. That reuse is disclosed here. The participant should retain the original archive and organiser's exact build-window announcement to support accurate provenance. If organisers disallow the reuse of pre-window generated assets or helpers, remove or recreate those items according to their instructions.

## Event-window AI assistance

After the participant stated on 2026-11-08 that the official build window had started, ChatGPT assisted with designing, generating, editing and debugging substantial portions of the API, database integration, authentication, content extraction, deterministic verification, review/decision flows, frontend source, tests and documentation. ChatGPT also helped interpret test failures and prepare the evaluation report. This assistance must be disclosed as significant AI assistance; it must not be represented as code written unaided by the participant.

The participant is responsible for reviewing and understanding the code, checking licences, testing it on their own machine, modifying it as needed, making the final technical decisions and truthfully explaining their own contribution. The source and commit history should accurately reflect the actual development process. Do not fabricate commits, timestamps, authorship or test results.

## Material and provider register

| Material / service | Source | Use in current build | Licence / data-handling note | Disclosure |
|---|---|---|---|---|
| Phase 00/01 planning, requirements and design documents | ChatGPT-assisted, based on participant-supplied project/problem documents | Product/engineering plan | Not a third-party software package | Pre-window AI-assisted planning material; retained and disclosed |
| ORBITA synthetic Brand Knowledge Pack and fixture assets | ChatGPT-assisted synthetic content; fixture helper from starter | Demo and regression evaluation | Synthetic, not customer/third-party brand data | Pre-window generated assets/helpers reused; disclose and confirm organiser permission |
| Event-window Python API/application code | ChatGPT-assisted implementation and debugging | Backend MVP | Participant must review; dependencies have individual licences | Significant build-window AI assistance |
| Event-window frontend source | ChatGPT-assisted implementation and debugging | Next.js UI source | Dependency licences to be retained in lockfile after install | Significant build-window AI assistance; build not yet verified |
| FastAPI, Pydantic, SQLAlchemy, Alembic, pypdf, python-docx, Pillow, pytesseract, PyJWT and other Python dependencies | Open-source packages pinned in `pyproject.toml` | API, persistence, extraction, OCR and security | Review package licences and current versions before submission | Dependency list is disclosed in `pyproject.toml` |
| Next.js, React, TypeScript, Tailwind CSS and Lucide React | Open-source packages declared in `apps/web/package.json` | Frontend | No lockfile generated yet; run npm install and retain package-lock before final submission | Dependency declarations disclosed; exact resolved versions not yet captured |
| Tesseract OCR | Local system package installed by participant | PNG/JPG OCR | Local processing; system package/licence version should be recorded on demo machine | No hosted OCR provider or external upload |
| Hosted LLM / embeddings / external AI API | None used by current MVP | Not applicable | No confidential content sent to a hosted model by this application | Not used |
| Postgres/pgvector and MinIO | Docker Compose scaffold only | Not used by current runtime | Not active or connected to API | Do not claim active integration |

## Current contribution statement (participant should personalise truthfully)

The participant is the sole project owner and is responsible for product direction, architecture decisions, integration, testing, validation, final changes, deployment and the final demonstration, to the extent those tasks they personally perform. ChatGPT provided significant coding, debugging, documentation and planning assistance as listed above. The participant should only claim implementation, testing, deployment or design tasks they have personally checked and can explain.

## Update protocol

For each added dependency, model, dataset, API, template, generated asset or service, record its name/version, source, licence/terms, purpose, date introduced, data sent/retained, cost limit, fallback and AI involvement. Preserve dependency lockfiles, service settings and source references. Do not upload real confidential brand materials to third-party providers without the brand's permission and a verified data-handling basis.
