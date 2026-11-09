# ADR-0001: Modular Monolith with Ports and Adapters

- Status: Accepted as the event-build architecture baseline; exact package versions are pinned in Phase 02.
- Date: 2026-11-08
- Context: Inkloom Sigillum must support a substantial evidence, versioning and review workflow while remaining feasible for a single-participant build. Premature microservices would add deployment and operational complexity before throughput or isolation requirements justify them.

## Decision

Build one modular monolith with strong internal boundaries:

- One Next.js App Router application.
- One FastAPI application.
- One worker process for durable background work.
- One PostgreSQL database with pgvector and full-text search.
- One S3-compatible object store for originals and large derived artefacts.
- One shared typed contract generated from OpenAPI or maintained with drift tests.

Inside the backend, use ports-and-adapters boundaries:

1. **Domain:** pure entities, value objects, enums and policy functions. No FastAPI, ORM, SDK or model-provider imports.
2. **Application:** explicit use cases and ports (for example CreateSubmission, BuildKnowledgePackVersion, RunReview, AcceptPatch and RecordDecision).
3. **Modules:** business capabilities with explicit public interfaces.
4. **Infrastructure:** PostgreSQL repositories, object storage, OCR, embeddings, LLM adapters, notifications and telemetry.
5. **API:** thin handlers that authenticate, validate, invoke a use case and serialise typed output.
6. **Frontend:** typed API client and explicit UI state; it does not duplicate adjudication or approval rules.

## Stack baseline to evaluate and pin in Phase 02

- Frontend: Next.js App Router, React, TypeScript, Tailwind CSS, shadcn/ui and Lucide.
- API: Python, FastAPI and Pydantic.
- Persistence: PostgreSQL + pgvector; SQLAlchemy 2.x and Alembic.
- Workflow: LangGraph with durable PostgreSQL checkpointing when Phase 11 is reached.
- Jobs: PostgreSQL job table, leases, idempotency and `FOR UPDATE SKIP LOCKED` when Phase 11 is reached.
- Files: local development adapter and S3-compatible deployment adapter.
- Parsing: pypdf, python-docx and Pillow; rendering/OCR chosen after benchmark.
- Quality: pytest, Playwright, Docker Compose, structured logs and traces.

## Consequences

- Domain tests run without a database, FastAPI or an LLM provider.
- Provider changes do not change domain rules.
- The transactional database remains the source of truth; object storage holds binaries and derived artefacts.
- Content-version creation and durable job enqueue must later be atomic through a transaction/outbox boundary.
- Stable UUIDs and explicit content/version hashes identify records; mutable filenames never identify versions.
- Split services only when measured throughput, security isolation or deployment evidence justifies it.

## Non-decisions

This ADR does not select a commercial LLM, embedding model, OCR engine, hosting provider or identity vendor. Those require a provider register entry, licence/data-handling review and evaluation before adoption.
