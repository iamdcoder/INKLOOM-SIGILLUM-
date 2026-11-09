# Phase 06 — Document parsing, OCR and visual-region extraction

**Build:** 018  
**Baseline:** Build 017  
**Implementation status:** **CORE COMPLETE — advanced extraction boundaries explicitly deferred**  
**External operational acceptance:** Pending PostgreSQL CI, live scanner/storage services and browser E2E verification.

## Scope and acceptance map

| Master-plan requirement | Build 018 implementation | Evidence / boundary |
|---|---|---|
| PDF logical parsing | PyMuPDF page reading order, page text and line spans; source page size, rotation and rendered-page dimensions retained. Table structures are extracted as best-effort metadata without duplicating canonical text. | `backend/sigillum/modules/content/extraction.py`; extraction unit tests. |
| Rendered PDF source locations | Searchable text lines receive quadrilateral polygons mapped through page rotation into rendered-page pixels. Source offsets are rebased into the immutable version text. | Rotated-PDF geometry tests; page preview API integration test. |
| Scanned PDF OCR | Pages with fewer than 20 extractable non-whitespace characters are OCR candidates. Tesseract runs at bounded render scale, per-file page cap and timeout; output retains line/word geometry, confidence, language and engine metadata. Empty, low-confidence, timeout, language-pack and page-limit paths remain explicit warnings/partial states. | Mocked unit coverage and a real local scanned-PDF smoke test. OCR is not guaranteed for every language; language data must be installed. |
| DOCX logical parsing | Body paragraphs/headings, ordered table rows/cells, runs, headers/footers and inline image metadata/alt-text presence are represented with exact logical character offsets. | DOCX fixture/unit test checks each region slice against the canonical extracted text. |
| DOCX rendered geometry | Not claimed. Coordinates are explicitly logical Unicode offsets; a document renderer is required before page coordinates can be represented. | Explicit warning in extraction manifest. |
| TXT parsing | UTF-8/UTF-8-BOM content preserves line breaks and line offsets; undecodable files return partial extraction. | Existing TXT unit/integration coverage. |
| PNG/JPG metadata and OCR | EXIF-corrected preview dimensions and source dimensions, pixel SHA-256, versioned dHash, palette inventory, local OCR word/line polygons, confidence and language/engine metadata. | Image extraction and review-workbench region tests. |
| Palette and contrast | Palette comparison is emitted only under an approved in-scope policy. Per-OCR-line contrast reports `PASS`, `FAIL` or `UNMEASURABLE` and records samples/method/limitations. Failures or uncertainty go to human review; they are not automatic certification. | Contrast, policy-scope and manual-review regressions. |
| Asset similarity | Exact SHA-256 remains the only deterministic identity match. Perceptual dHash nominates possible similar assets for human inspection only. | dHash distance and review-candidate tests. |
| Source-region review | Workbench navigates to image OCR polygons and PDF page regions. PDF page previews are served by an authenticated, access-checked, SHA-256-verified API route. DOCX/TXT findings navigate to exact logical spans. | API integration test for PDF page preview; source mapping tests; frontend TSX parser check. |
| Failure and uncertainty | OCR timeout, absent text, page cap, low confidence, unsupported geometry and unmeasurable contrast remain visible warnings or manual-review states. No failure path is an approval. | Unit, integration and golden-case regression. |

## Phase 06 gate result

**Core implementation gate: PASS.** The core extraction path now has source-mapped PDF/TXT/DOCX and raster-image extraction, scanned-page OCR, page preview, and reviewer source navigation without claiming unsupported geometry or certainty.

- Backend/unit/integration suite: **155 passed, 2 skipped, 0 failed** (157 collected).
- The two skips require PostgreSQL for RLS and concurrent publication/version locking.
- Python compilation: `python -m compileall -q backend migrations tests scripts` passed.
- SQLite Alembic migration head: `20261109_0007`; extraction manifests need no new relational migration.
- Synthetic golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** across 12 deterministic cases.
- Local OCR smoke test: a generated scanned PDF extracted `SAVES UP TO 40 PERCENT` at 95.6% average confidence with installed Tesseract English data.
- TypeScript parser: 17 frontend `.ts` / `.tsx` files parsed with zero syntax diagnostics. This is not a complete typecheck or build.

**External operational gate: PENDING.** Full Next.js lint/typecheck/production build and browser E2E could not be run because the local dependency install is incomplete and the clean install attempt timed out. Live PostgreSQL RLS/concurrency, ClamAV and S3/MinIO also require external services/CI.

## Deliberate deferrals

1. DOCX renderer-backed page geometry. The current source mapping is logical offsets only.
2. OCR of separately embedded images/logos within an otherwise searchable PDF, and pixel OCR of DOCX-embedded images. Their presence/alt-text is exposed where available; manual review remains explicit.
3. Broad multilingual OCR evaluation and adversarial corpus benchmarking. `TESSERACT_LANG` is configurable, but only installed language packs can run.
4. PDF table cell geometry/offsets remain best-effort metadata; canonical source navigation uses page text/OCR line regions.
5. Perceptual similarity and palette checks remain candidate signals; no model or embedding output can certify logo identity or brand fit.
6. Full browser interaction regression, live external-service verification and complete frontend production build.

## Next phase

Build 018 is the baseline for **Phase 07 — Knowledge normalisation, temporal truth and indexing**. The Phase 06 core gate is closed; the advanced items above remain explicitly tracked and must not be presented as completed capabilities.
