# Phase 08 — Hybrid evidence retrieval and source ranking

**Status: PARTIALLY IMPLEMENTED**

## Implemented in Build 008

- Approved-only evidence candidate retrieval.
- Brand and contextual scope filtering for offer, geography, channel, locale and audience.
- Subject relevance filtering.
- Independent lexical and structured candidate rankings.
- Reciprocal Rank Fusion (RRF) with deterministic tie-breaking.
- Temporal eligibility applied before a candidate can support a claim.
- Source precedence and equal-top-precedence conflict preservation in deterministic adjudication.
- Reviewer-facing retrieval and temporal provenance: method, ranks, RRF score, valid time, record time and authority.

## Still outstanding

- PostgreSQL full-text search and pgvector vector retrieval.
- Embedding generation/versioning and model metadata.
- Hybrid lexical/vector RRF and optional cross-encoder reranking.
- HNSW versus exact filtered-search benchmark harness.
- Recall@5 / MRR evaluation against a larger labelled query set.
- Negative cross-tenant, expired-record and unapproved-record retrieval leakage tests against the production database adapter.

## Honest capability statement

The current method is named `lexical+structured_rrf`. It is not vector retrieval. The API and review evidence explicitly report `vector_search = NOT_CONFIGURED`; a high RRF score is a retrieval ranking, not an evidence-sufficiency verdict or proof of a claim.

## Gate evidence

- `tests/unit/test_temporal_retrieval.py`
- `tests/unit/test_verification_engine.py`
- `tests/integration/test_api.py`
- `reports/golden_evaluation_latest.json`
- `docs/technical/BUILD_008_TEMPORAL_TRUTH_RETRIEVAL.md`
