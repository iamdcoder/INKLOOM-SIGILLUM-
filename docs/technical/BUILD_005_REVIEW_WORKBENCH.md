# Build 005 — Review Workbench triage and provenance

**Date:** 8 November 2026  
**Scope:** Frontend-only enhancement to the existing review page. The verification engine, persisted findings, patch API, content-version model and reviewer decision endpoints are unchanged.

## Implemented

### Finding triage
- Search finding title, explanation, category, verdict, reason code and exact content quote.
- Filter by severity, category, verdict and resolution status.
- Sort by risk (default), confidence high-to-low, confidence low-to-high or category.
- Show the number of visible findings against the total and provide a clear-filter action.
- Keep the summary counters based on the complete finding set, not the currently filtered subset.

### Finding-to-content navigation
- A finding with exact text offsets exposes a **Locate exact span** action.
- The action scrolls the corresponding span into view and applies a visible active outline.
- Findings without exact text offsets do not receive fabricated locations; the user is told to inspect the original asset or region metadata instead.

### Evidence provenance
Evidence cards now display available fields from the existing evidence records: source/fact/term identifier, source version, source quote or rule rationale, approved value/unit/qualifier, validity dates, scope and authority rank. Missing fields remain omitted.

### Extraction region metadata
Where a finding has a region record, the UI shows the supplied region kind, page number, OCR bounding box and extraction confidence. It explicitly explains that coordinates are shown only when supplied by extraction. The interface does not invent PDF/image coordinates or claim to render a complete visual overlay.

## Deliberate limitations
- PDF preview remains the browser's native PDF view; the current build does not map text highlights onto rendered PDF coordinates.
- Image preview is present, but finding-level boxes are not yet drawn over the image.
- Source evidence is shown with identifiers and provenance metadata; a separate source-file viewer/deep-link is not yet implemented.
- Search/filtering is client-side over the current review's findings.

## Manual acceptance checklist
1. Open a review with multiple findings.
2. Search for a word contained in a finding title, explanation, category, reason code or quote.
3. Filter by each severity, category, verdict and status option.
4. Confirm the visible/total count updates and Clear filters restores all findings.
5. Change sorting and confirm risk-first is the default.
6. Expand a finding with offsets and select **Locate exact span**; verify the source snapshot scrolls to and highlights the matching text.
7. Expand findings with fact evidence and confirm the source version, quote, value, validity, scope and authority rank are shown only when present.
8. Inspect an OCR finding with region metadata; verify that only supplied region details are displayed.
9. Confirm that the backend smoke test still passes and decision blocking/approval semantics are unchanged.

## Validation boundary
The updated TSX file passed TypeScript syntax transpilation with zero syntax diagnostics in the build environment. This is not a substitute for the project's full ESLint, TypeScript typecheck or Next.js production build. Run all three commands in the participant's Windows environment before treating Build 005 as frontend-verified.
