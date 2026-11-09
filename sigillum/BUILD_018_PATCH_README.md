# Inkloom Sigillum — Build 018 patch notes

**Baseline:** Build 017  
**Phase implemented:** Phase 06 — Document parsing, OCR and visual-region extraction  
**Local backend result:** 155 passed, 2 skipped, 0 failed

## Delivered

- Rotation-aware PDF line-region polygons using rendered-page pixel coordinates.
- Bounded scanned-PDF OCR through local Tesseract, with page cap, timeout, configurable language and explicit uncertainty warnings.
- Authenticated, access-controlled, hash-verified rendered PDF page preview endpoint.
- Review Workbench page navigation and text/OCR polygon selection for PDF sources.
- DOCX heading, paragraph, run, table-row, table-cell, header and footer offsets; inline-image dimensions and alt-text inventory.
- Exact UTF-8 TXT line offsets remain supported.
- Raster image dimension/orientation, pixel hash, dHash similarity candidate, palette inventory, OCR polygons and conservative local contrast estimates.
- Most-specific source-region resolution so DOCX run/cell evidence is preferred over broad containers.
- New regression coverage for rotated searchable PDF, scanned PDF OCR, DOCX offset integrity, image metadata, dHash candidates, region selection and PDF page preview.

## Verification

- Backend/unit/integration suite: **155 passed, 2 skipped, 0 failed**.
- Python compileall: passed.
- SQLite Alembic head: `20261109_0007`.
- Synthetic golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**.
- Real Tesseract OCR smoke: scanned PDF text extracted at 95.6% mean confidence.
- Frontend syntax parse: 17 TypeScript/TSX files, 0 syntax diagnostics.

## Outstanding / limitations

- Full frontend lint/typecheck/Next.js production build could not be run: local dependencies are incomplete and `npm ci` timed out. Syntax parse is not a typecheck.
- Two PostgreSQL-only tests are skipped in SQLite mode (RLS and concurrent publication/version locking).
- Live PostgreSQL, ClamAV, S3/MinIO and browser E2E checks remain pending.
- DOCX rendered-page coordinates and embedded-image OCR inside PDF/DOCX are intentionally deferred.
- Broad multilingual OCR and adversarial visual evaluation remain deferred. Only installed Tesseract language packs are usable.
- Palette and dHash outputs are candidate signals only; no automated logo certification.

See `docs/technical/BUILD_018_PHASE06_EXTRACTION.md` and `docs/phase-gates/PHASE-06-STATUS.md` for full detail.
