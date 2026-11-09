# Inkloom Sigillum — Build 008 Patch

**Base:** Build 007  
**Increment:** Temporal Truth and Evidence Retrieval  
**Date:** 2026-11-08

## Apply

Extract this archive directly into the existing `sigillum` repository root, preserving the folder paths. It contains only changed/new source, tests, documentation and reports. It does not include or replace `.env`, local databases, uploaded originals, `node_modules`, or the participant's `package-lock.json`.

No database migration is required.

## What changed

- Add `backend/sigillum/modules/retrieval/temporal.py` for distinct real-world valid time and knowledge-system record time.
- Add `backend/sigillum/modules/retrieval/evidence.py` for approved-only, contextual lexical + structured evidence candidate retrieval using Reciprocal Rank Fusion.
- Integrate temporal filtering, source precedence, equal-precedence conflict preservation and retrieval provenance into the deterministic savings-claim engine.
- Use `ReviewRun.created_at` as the review's knowledge-as-of boundary.
- Validate fact timestamp formats, timezone offsets and interval ordering before Knowledge Pack publication.
- Show valid/recorded time, temporal state, authority, retrieval ranks and RRF score in the Workbench evidence panel. Excluded temporal candidates are explicitly labelled as diagnostics, not proof.
- Add tests and update phase gates, requirement traceability, build activity and verification records.

## Verify backend (PowerShell, repository root)

```powershell
.\.venv\Scripts\Activate.ps1
python -m compileall -q backend tests
python -m pytest tests -q
python scripts/evaluate_golden_cases.py
```

Expected Build 008 results:

- Backend: **50 passed**
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**
- Fresh local HTTP vertical slice smoke: **8/8 checks passed** (see `reports/build008_live_smoke_verification.json`)

## Verify frontend

```powershell
cd apps\web
npm run lint
npm run typecheck
npm run build
```

These frontend checks must be rerun on the participant's Windows checkout after applying this patch. The packaging environment only performed TSX syntax transpilation for the changed page (zero syntax diagnostics); it did not run the full frontend dependency-based commands.

## Capability boundary

The retrieval method in this build is `lexical+structured_rrf`. The trace explicitly reports `vector_search = NOT_CONFIGURED`. PostgreSQL full-text search, pgvector, embeddings, HNSW, cross-encoder reranking and Recall@5/MRR benchmarking are not active. RRF ranking is not an evidence-sufficiency verdict and is not proof of a claim.

The valid-time/record-time resolver currently applies to the synthetic approved fact records used by the configured savings-claim analysis. Full normalized bitemporal database tables and equivalent lifecycle coverage for every knowledge record family remain outstanding.
