# Implementation architecture — current build

## Runtime shape

- **Web:** Next.js App Router, React, TypeScript and a custom dark-first design system.
- **API:** FastAPI `/api/v1`, Pydantic request contracts, request IDs, CORS and structured HTTP errors.
- **Application:** review use case coordinates extraction, deterministic analysis, immutable versions and audit records.
- **Domain/verification:** typed enums and pure deterministic functions; no provider/model SDK has authority to decide truth.
- **Persistence:** SQLAlchemy 2.x models with Alembic initial migration. Local default is SQLite for a reproducible two-day demo.
- **Binary storage:** local private filesystem under `STORAGE_ROOT`, with opaque version keys and SHA-256 metadata.
- **OCR:** local Tesseract via pytesseract for PNG/JPG.
- **Worker:** currently an entrypoint scaffold only. Reviews execute synchronously in the API process in this build.

## Review data path

1. Authenticated creator selects the brand/channel/publication context and uploads an allowed file.
2. API validates byte limit and file signature before parsing.
3. Parser extracts content. Text/page/word regions, warnings and OCR confidence are retained.
4. Original bytes are stored as an immutable content version with SHA-256.
5. The deterministic engine checks the supported savings-claim pattern, configured terminology, voice patterns, unmatched quantified durations and instruction-like text.
6. Image/PDF/DOCX visual limitations create explicit manual-review findings.
7. Findings are persisted against a review run and a Brand Knowledge Pack version.
8. Creator may propose a hash-bound local patch for TXT, or upload a new source file revision. Both paths create a new content version and review.
9. Reviewer/brand owner/admin records resolution notes and/or a version-bound decision. Approval is blocked while unresolved blocking or review-required findings remain; overrides are role-gated and require a reason.
10. Audit events retain material actions.

## Boundaries and non-claims

- The frontend displays server-owned verdicts; it does not adjudicate claims.
- The current engine covers only configured deterministic claim patterns. It is not general-purpose claim understanding.
- No external LLM, embedding service, hosted OCR provider or external data source is called by the current runtime.
- `infra/docker-compose.yml` is a Postgres/pgvector and MinIO development scaffold; the current API uses SQLite and local filesystem storage unless settings are deliberately changed and adapters verified.
- The LangGraph/durable job/checkpoint/event-streaming path is not active in this build.
- Single demo workspace only. Creator ownership is checked in application routes, but PostgreSQL RLS and production-grade tenant isolation are not implemented.
