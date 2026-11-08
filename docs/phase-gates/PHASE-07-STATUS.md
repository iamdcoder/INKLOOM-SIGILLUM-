# Phase 07 — Knowledge normalisation, temporal truth and indexing

**Status: PARTIALLY IMPLEMENTED**

## Implemented in Build 008

- Separate valid-time (`valid_from`, `valid_until`) and record/system-time (`recorded_at`/`recorded_from`, `recorded_until`/`superseded_at`) assessment.
- Publication time is evaluated independently from review knowledge-as-of time.
- Review orchestration supplies the persisted review creation timestamp as `knowledge_as_of`.
- A record not yet recorded or no longer recorded at that review time cannot be used as proof.
- Approved fact temporal metadata is checked for timezone-aware ISO-8601 values and non-inverted intervals before Knowledge Pack publication.
- Exact pack snapshot and fingerprint remain attached to each review for historical reconstruction.
- Unit tests cover current, future, expired, record-time unavailable and invalid interval cases.

## Still outstanding

- Normalized per-record bitemporal database tables and transactional mutation history.
- Full scope/temporal schema for policies, terminology, voice examples and approved assets.
- Source-document lineage and indexing lifecycle for all approved knowledge record types.
- Re-index/replay jobs and integrity checks for superseded source versions.
- Multi-tenant row-level security and production-grade data isolation.

## Gate evidence

- `tests/unit/test_temporal_retrieval.py`
- `tests/unit/test_knowledge_pack_store.py`
- `tests/integration/test_api.py`
- `docs/technical/BUILD_008_TEMPORAL_TRUTH_RETRIEVAL.md`

Do not mark this phase complete until all knowledge record families have governed temporal history and the review snapshot can reconstruct the exact authorized record set.
