# Build 008 — Temporal Truth and Evidence Retrieval

## Objective

This increment strengthens the Phase 07/08 foundation by making fact applicability bitemporal and by adding deterministic evidence-candidate retrieval before claim adjudication.

## Two independent time dimensions

Each fact can carry two intervals:

- **Valid time** (`valid_from`, `valid_until`): when the fact is true in the real world and can substantiate content intended for publication.
- **Record/system time** (`recorded_at` or `recorded_from`, `recorded_until` or `superseded_at`): when the fact exists in the governed knowledge record.

The engine evaluates valid time against the submission's `publication_at`. The orchestration layer passes the persisted `ReviewRun.created_at` as `knowledge_as_of`. A fact recorded after the review timestamp, or no longer present in the record-time interval, is not eligible as proof for that review. The immutable Knowledge Pack snapshot and fingerprint remain attached to the review.

Legacy records with no record-time values remain usable for compatibility but are explicitly marked `LEGACY_RECORD_TIME_UNKNOWN` in evidence provenance. New or edited facts with temporal fields must use timezone-aware ISO-8601 timestamps. Invalid or inverted intervals fail closed.

## Evidence candidate retrieval

`backend/sigillum/modules/retrieval/evidence.py` provides a local, dependency-free retrieval baseline:

1. Require approved fact status.
2. Apply brand, offer, geography, channel, locale and audience scope filters. A record-specified dimension missing from the review context fails closed. An omitted record dimension remains a broader scope, rather than being treated as a hidden requirement.
3. Check subject relevance against the claim text.
4. Assess valid-time and record-time eligibility.
5. Produce independent lexical and structured rankings.
6. Combine their ranks using Reciprocal Rank Fusion (RRF), with `k = 60`.
7. Preserve deterministic tie-breaking by fact ID.

The output records the retrieval method, lexical rank, structured rank, RRF score and temporal state. These outputs identify candidates; they do not themselves establish truth. The verification engine still applies source precedence, equal-authority conflict handling, exact numeric/qualifier checks and extraction-confidence gates.

## Source precedence and conflict handling

`source_precedence` is accepted as the preferred numeric field; `authority_rank` remains the compatibility field. Higher numeric values have higher precedence. Only the highest applicable precedence group is used for decisive comparison. If multiple records at that top rank disagree materially, the result remains `CONFLICTING`; retrieval order is never used to choose one.

## Reviewer evidence panel

The Workbench now displays available valid-time and record-time fields, temporal state, source precedence, retrieval method, lexical/structured ranks and RRF score. Historical/future/record-time-excluded candidates are visibly labelled **TEMPORAL DIAGNOSTIC — NOT USED AS PROOF**.

## Configuration and replay

Reviews created by this build record `analysis_config_version = deterministic-temporal-rrf-v2`. The full Knowledge Pack snapshot and fingerprint remain unchanged in the review record. No database migration is required; this change uses the existing JSON `evidence` field and review snapshot storage.

## Verification

- Unit tests cover current, future, expired, not-yet-recorded, no-longer-recorded and invalid temporal intervals.
- Retrieval tests cover approved-only filtering, scope filtering, deterministic RRF trace and metadata.
- Engine tests cover record-time abstention, source provenance, and higher-precedence selection.
- Existing end-to-end submission, correction and approval tests remain part of the complete suite.
- Synthetic golden evaluation remains 11 automated PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL.

## Honest limitations

- Retrieval in this increment is **lexical + structured RRF**, not lexical + vector RRF. `vector_search` reports `NOT_CONFIGURED` explicitly. PostgreSQL full-text search, pgvector, embeddings and HNSW are not active integrations.
- The resolver currently handles the synthetic approved-fact schema and the configured savings-claim predicate. It is not a general-purpose semantic evidence engine for arbitrary fact types.
- Knowledge Pack records remain in the filesystem-backed immutable pack adapter. Record-time fields are supported in the record schema, but there is no normalized bitemporal database table or distributed write transaction.
- Exact evidence sufficiency still depends on the deterministic claim patterns already implemented; similarity or RRF rank never turns into proof by itself.
- The single demo workspace is not production-grade multi-tenant isolation or PostgreSQL RLS.

## Phase status

Phase 07 is **partially implemented**: scoped valid-time/record-time resolution, immutable review snapshots and pack-level temporal validation exist; normalized database history, indexing lifecycle and broad temporal coverage remain pending.

Phase 08 is **partially implemented**: deterministic lexical + structured RRF exists locally; vector retrieval, pgvector, query benchmarks and cross-tenant retrieval leakage testing remain pending.
