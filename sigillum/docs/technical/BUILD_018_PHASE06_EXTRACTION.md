# Build 018 — Phase 06 extraction implementation record

**Product:** Inkloom Sigillum  
**Build:** 018  
**Baseline:** Build 017  
**Phase:** 06 — Document parsing, OCR and visual-region extraction  
**Migration head:** `20261109_0007` (no new tables required)

## 1. Outcome

Build 018 closes the Phase 06 core implementation path. The extractor now returns a canonical text string plus a provenance-preserving region manifest. Regions use stable IDs and explicit coordinate systems: Unicode character offsets for logical document locations, or top-left-origin rendered-page/image pixels for visual regions. A finding span is associated with the smallest containing region so a DOCX run or table cell is preferred over its broad paragraph or row container.

## 2. PDF extraction and review

- PyMuPDF extracts searchable text in sorted page order and emits page-line spans with polygons.
- PDF polygons are transformed through `page.rotation_matrix`; width/height and coordinates use the exact rendered page pixel dimensions. Original page dimensions and rotation are also retained.
- Pages with fewer than 20 non-whitespace extractable characters are scanned-page OCR candidates.
- Page rasterisation is bounded by `PDF_RENDER_DPI` and `PDF_RENDER_MAX_DIMENSION`. OCR is bounded by `PDF_OCR_MAX_PAGES` and `OCR_TIMEOUT_SECONDS`.
- `TESSERACT_LANG` selects the installed OCR language packs (default `eng`; a multi-language value such as `eng+hin` is supported by Tesseract when those packs are installed).
- PDF OCR output stores text offsets, word boxes, line polygons, average confidence, language and engine version. Low confidence, empty OCR, OCR timeout/provider errors and page-limit exhaustion remain explicit warnings and produce a partial extraction where appropriate.
- `GET /api/v1/content-versions/{version_id}/pages/{page_number}/preview` authorises the version, requires a CLEAN scan, verifies the original SHA-256 and renders only the requested page. The Review Workbench overlays line polygons on this page preview and navigates from linked findings.
- PDF table extraction is best-effort metadata. The page line regions remain the canonical source-text locations to avoid duplicate table text in review.

## 3. DOCX and TXT extraction

- DOCX parsing walks the body in document order and preserves headings, paragraphs, runs, table rows, table cells, headers and footers with exact logical character offsets.
- Inline image inventory records image dimensions in EMU and alt-text presence/value. Embedded pixels are not OCRed in this build.
- No rendered DOCX page coordinates are fabricated. The extractor returns `unicode-character-offsets` and `coordinates_available: false` until a document renderer is adopted.
- TXT uses UTF-8/UTF-8-BOM and retains line breaks and line offsets. Undecodable content is represented as partial extraction rather than silently decoded with replacement characters.

## 4. Raster image and visual candidates

- PNG/JPG use EXIF-transposed raster dimensions, original dimensions, a decoded-pixel SHA-256 fingerprint and a descriptive dominant palette.
- Tesseract returns OCR lines and per-word boxes/polygons with confidence, language and engine version.
- Contrast is estimated conservatively for individual OCR regions only when an approved in-scope policy threshold exists. `PASS`, `FAIL` and `UNMEASURABLE` include measurement context and limitations.
- Approved usage palette rules can produce a bounded RGB-distance comparison. A versioned 64-bit dHash is stored for similarity candidates. Exact SHA-256 remains the deterministic asset identity check; dHash/palette are not conclusive identity or compliance decisions.
- Findings from palette/contrast/perceptual signals route to human inspection. They do not independently establish a blocking verdict, approval or logo identity.

## 5. Configuration

| Setting | Default | Meaning |
|---|---:|---|
| `TESSERACT_CMD` | `tesseract` | Executable path. |
| `TESSERACT_LANG` | `eng` | Installed language pack(s); multiple packs use Tesseract `+` notation. |
| `OCR_TIMEOUT_SECONDS` | `20` | Maximum time for a local OCR call. |
| `PDF_RENDER_DPI` | `144` | Requested PDF rasterisation DPI, bounded in settings. |
| `PDF_RENDER_MAX_DIMENSION` | `2400` | Maximum rendered page dimension. |
| `PDF_OCR_MAX_PAGES` | `20` | Maximum scanned pages OCRed per file; `0` disables scanned-PDF OCR. |

Missing Tesseract binaries/language data or OCR runtime failure is surfaced as an extraction warning/partial status. It is never treated as successful extraction.

## 6. Tests and verification

- Backend/unit/integration suite: **155 passed, 2 skipped, 0 failed**. The skipped tests require PostgreSQL for row-level security and concurrent publication/version locking.
- `python -m compileall -q backend migrations tests scripts`: passed.
- `alembic heads` and `alembic upgrade head`: migration head `20261109_0007`.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**.
- Real local scanned-PDF OCR smoke: extracted `SAVES UP TO 40 PERCENT` with 95.6% confidence.
- TypeScript syntax parse: 17 frontend `.ts` / `.tsx` files, zero parse diagnostics.
- Full frontend lint/typecheck/build: not verified. The local `node_modules` is incomplete and `npm ci` timed out. Browser E2E not run.
- Live PostgreSQL, ClamAV and S3/MinIO: not run locally.

## 7. Boundaries and deferred work

DOCX renderer-backed page geometry, OCR of embedded PDF/DOCX images, broad multilingual/adversarial OCR evaluation, robust visual logo recognition and browser-level E2E remain deferred. Page geometry in PDF and image OCR overlays are implemented. Reviewers must treat all OCR/palette/contrast/perceptual results within their documented limitations.

See `docs/phase-gates/PHASE-06-STATUS.md` for the requirement-by-requirement gate and outstanding external acceptance checks.
