# Build 013 — Transactional Knowledge Pack catalogue

## Objective

Build 012 made Knowledge Packs tenant+brand isolated, but the authoritative pack version pointer and draft state still lived in JSON files guarded by a process-local lock. That storage model is unsuitable when multiple API processes or restarts operate on the same brand. Build 013 moves the catalogue and draft lifecycle into the database while preserving the existing service/API contract and private binary asset storage.

## Database model

Alembic revision `20261109_0004` creates four tables:

| Table | Responsibility |
|---|---|
| `brand_knowledge_pack_heads` | One row per tenant+brand; points to the active immutable version and carries a monotonically increasing revision. |
| `brand_knowledge_pack_versions` | Immutable version metadata and complete JSON snapshot, with source version, pack version, fingerprint, actor and timestamp. |
| `brand_knowledge_pack_drafts` | Mutable working snapshot, validation result, base version/fingerprint, publication status and optimistic revision. |
| `brand_knowledge_pack_decisions` | Append-only owner decisions for individual facts, policies, terminology, sources and assets. |

Every table is tenant+brand scoped. The PostgreSQL migration enables and forces row-level security with a policy matching both `app.tenant_id` and `app.brand_id`. `KnowledgePackStore` sets those values before every database transaction. SQLite does not provide RLS; local tests validate scope predicates and application-level authorization but do not prove PostgreSQL enforcement.

## Source-of-truth boundaries

- Database rows are authoritative for the active pointer, immutable JSON snapshots, draft state, validation and record-decision history.
- `data/brand_packs/` JSON snapshots, the active pointer and draft JSON files are compatibility/export mirrors. The database can reconstruct the active local mirror when it is absent.
- Uploaded brand asset bytes remain in the configured private storage adapter. The Knowledge Pack snapshot stores scoped metadata, SHA-256, provenance and the storage key, not public URLs.
- Reviews continue to retain the exact Knowledge Pack snapshot/fingerprint used at review time. A pack publication does not rewrite historical review context.

## Concurrency and state transitions

### Draft edits

Each draft has a `revision`. A write includes the revision read by the editor and updates only when the stored revision still matches. The update predicate is equivalent to:

```sql
UPDATE brand_knowledge_pack_drafts
SET snapshot = :snapshot, revision = :expected_revision + 1
WHERE tenant_id = :tenant_id
  AND brand_id = :brand_id
  AND draft_id = :draft_id
  AND revision = :expected_revision;
```

A row count other than one is reported as a stale-draft conflict. This compare-and-swap is used in addition to PostgreSQL `SELECT FOR UPDATE`; it also protects the local SQLite path where `FOR UPDATE` is not implemented.

### Publication

Publication locks the tenant+brand head and draft row on PostgreSQL, revalidates the draft and verifies that the active version/fingerprint still match the draft base. It inserts a new immutable version and conditionally advances the head using its current version and revision. If the update loses a race, the transaction fails rather than silently publishing over another version. The local active JSON pointer is written after the DB commit and is explicitly only a compatibility mirror.

### Record decisions

A decision updates the record inside its draft and creates a separate `brand_knowledge_pack_decisions` row with status, reason, actor and timestamp in the same transaction. `GET /api/v1/brands/current/drafts/{draft_id}/decisions` returns the scoped history to Brand Owners, Reviewers and Administrators. The record does not become authoritative for review until the containing draft is successfully validated and published by a Brand Owner.

## Build 012 compatibility

On first scoped access after the migration:

1. If a database head already exists, it is used as the source of truth and the local active mirror is repaired.
2. If no head exists but a Build 012 filesystem active pointer exists, the full published version history is imported into the database. Each version snapshot fingerprint and the active-pointer fingerprint are checked before import; an inconsistent history fails closed. The original ORBITA legacy tenant-only pack is still only migrated into the ORBITA brand namespace.
3. Eligible Build 012 JSON drafts in the brand-scoped draft folder are imported into `brand_knowledge_pack_drafts`. A draft is imported only when its ID matches its filename, its brand matches the requested scope, its snapshot is an object, and it has a base version and fingerprint. Existing DB drafts are not overwritten. Malformed files are left untouched for manual recovery.
4. Future reads and writes use the database. Filesystem JSON continues to be updated as a compatibility mirror.

## API surface

Existing endpoints remain stable:

- `GET /brands/current/management` — active snapshot, metadata and version history.
- `POST /brands/current/drafts` — create draft.
- `GET /brands/current/drafts/{draft_id}` — read draft.
- `PUT /brands/current/drafts/{draft_id}/section` — replace one supported section. Stale concurrent writes return `409 STALE_DRAFT_REVISION`.
- `POST /brands/current/drafts/{draft_id}/validate` — validate full draft.
- `POST /brands/current/drafts/{draft_id}/publish` — guarded immutable publication.
- `POST /brands/current/drafts/{draft_id}/records/{record_type}/{record_id}/decision` — record an owner decision with a mandatory reason.
- `GET /brands/current/drafts/{draft_id}/decisions` — inspect append-only decision history.

## Verification performed

- Backend test suite: **99 passed, 1 skipped** (100 collected) in the local SQLite environment. The skipped case requires live PostgreSQL to exercise RLS.
- Database lifecycle: fresh migration to `20261109_0004`, all catalogue tables present, repeated upgrade remains current.
- Brand management integration tests: active version reload from a fresh store root; stale draft compare-and-swap rejects a lost update; Build 012 filesystem draft is recovered into the DB catalogue; full published version history and its active pointer are imported with fingerprint validation; decision history is readable; publish lifecycle still creates immutable v0002.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** over 12 synthetic fixtures.
- `scripts/verify_database.py`: SQLite schema current at `20261109_0004`, all 16 required tables present; RLS reported `not_applicable` as expected for SQLite.
- Python compileall: passed for backend, apps, migrations, tests and scripts.

## Explicitly unverified / deferred

- Live non-superuser PostgreSQL RLS and concurrent publication test.
- Live MinIO/AWS object-storage integration.
- Controlled PDF/DOCX Knowledge Pack source import and malware quarantine.
- Rich typed authoring forms, extended asset policy, conflict validation and visual version diff.
- Full Next.js lint/typecheck/production build after Build 011/012 UI changes. Build 013 makes no frontend source changes.

Do not mark Phase 04 complete until its remaining gate items in `docs/phase-gates/PHASE-04-STATUS.md` are met.
