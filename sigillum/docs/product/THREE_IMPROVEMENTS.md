# Three measurable improvements

These are the three improvements committed for the build. The measurements below describe the current synthetic demo corpus and implementation limits; they are not claims of production accuracy.

## 1. Proof Ledger — provenance that survives review

**Problem addressed:** a fluent warning is not useful unless a reviewer can inspect the exact content, the source record and the governing context.

**Implementation in this build:** each finding stores its code, category, severity, verdict, reason code, evidence sufficiency, confidence, extraction confidence, text offsets/quote or region, evidence references, and the review's content hash and Knowledge Pack version. The reviewer interface exposes the span and evidence context.

**Acceptance tests:** `tests/unit/test_verification_engine.py`; `tests/integration/test_api.py`; patch/revision hash tests.

**Target metric:** 100% of findings created by configured checks include a stable reason code and a content quote/span or an explicit no-span/manual-review state. Claim findings that rely on approved facts include source IDs and version/validity context.

**Limit:** this MVP does not yet snapshot every full Knowledge Pack JSON record into an immutable database evidence snapshot. The seed pack is a versioned local fixture; database-backed pack governance is Phase 04/07 work.

## 2. Scope-Time Truth Resolver — facts are valid only in context

**Problem addressed:** a claim can be correct for a different offer, region, channel, audience or period without being valid for this publication.

**Implementation in this build:** configured approved savings facts are filtered by required offer, geography, channel, locale, audience and publication time. Missing required context fails closed. Expired facts produce `STALE`; future-effective facts produce `UNVERIFIABLE` with `FACT_NOT_YET_VALID`; equally authoritative conflicting values produce `CONFLICTING`.

**Acceptance tests:** GOLD-001 through GOLD-005; missing-scope and future-effective unit tests.

**Target metric:** 100% pass on the currently implemented temporal/scope golden cases. The current report is generated at `reports/golden_evaluation_latest.json`.

**Limit:** this is a deterministic rule for configured fact types, not a universal natural-language entailment engine. Bitemporal record-time replay, source-precedence administration and broad atomic-claim extraction remain future work.

## 3. Pixel-to-Claim Continuity — image text enters the same review pipeline

**Problem addressed:** claims embedded in static creative should not bypass the content review used for ordinary copy.

**Implementation in this build:** PNG/JPG files are passed through local Tesseract OCR. Word regions retain offsets, bounding boxes and extraction confidence. Extracted text then enters the same percentage-claim, terminology, tone and untrusted-instruction checks. Low-confidence extraction forces manual review. Logo identity and contrast are not automatically certified; explicit review-required findings prevent silent approval.

**Acceptance tests:** GOLD-008; image extraction tests; image upload integration test.

**Target metric:** every image submission creates an OCR extraction record and, regardless of OCR success, explicit visual asset and contrast review gates. High-confidence extracted numeric claims use the same deterministic adjudicator as text files.

**Limit:** the current build does not perform logo matching, pixel-level palette analysis, standards-grade contrast calculation, scanned-PDF OCR or complete embedded-image extraction from PDF/DOCX. These are disclosed as manual-review items or future scope, never reported as passed checks.
