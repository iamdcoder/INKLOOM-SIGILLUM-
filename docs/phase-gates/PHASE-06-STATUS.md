# Phase 06 — Document parsing, OCR and visual-region extraction

Status: **PARTIAL — Build 006 implementation increment**

## Implemented

- TXT line-level source mapping with Unicode character offsets.
- DOCX paragraph and table-row offsets; no rendered coordinates are fabricated.
- PDF page text ranges and media-box dimensions; rendered text polygons are not yet available.
- PNG/JPG image dimensions, format, EXIF orientation, decoded-pixel SHA-256 and dominant-colour inventory.
- OCR line regions with stable region IDs, text offsets, per-word boxes, polygon points, normalized bounding boxes, top-left pixel coordinate metadata, Tesseract engine/version, bounded timeout and confidence.
- Conservative local contrast estimate for OCR lines when an approved in-scope contrast threshold exists. Each result records `PASS`, `FAIL` or `UNMEASURABLE`, sample colours, method and limitations.
- Workbench overlay and click selection for image OCR polygons, plus links from region-backed findings to the relevant inspector.
- Human-review routing for measured failures and in-scope unmeasurable regions. No local measurement independently approves content or creates a definitive blocking decision.

## Still required before Phase 06 exit

- Controlled PDF rasterisation and scanned-page OCR with per-page rotation/coordinate tests.
- Rendered PDF region polygons and robust mapping for crop offsets/rotation.
- DOCX renderer-backed page/region geometry.
- Approved asset exact-hash matching and perceptual candidates with human confirmation.
- Owner-configured palette/geometry tolerances and measured palette comparison.
- Broader OCR language, confidence and adversarial fixture evaluation.

## Acceptance evidence

- Backend unit and integration suite: 33 passed in the Build 006 package.
- Frontend TSX syntax transpilation: zero syntax diagnostics.
- Developer must rerun `npm run lint`, `npm run typecheck` and `npm run build` after applying the patch.
- Reviewer must verify an image submission with overlays in the browser.

Do not mark Phase 06 complete until exact source-region navigation is verified for image regions, PDF pages and DOCX/TXT logical locations, and all listed exit requirements are addressed or explicitly deferred by release scope.
