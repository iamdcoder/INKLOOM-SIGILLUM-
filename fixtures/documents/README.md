# Fixture corpus

All fixture content is synthetic and test-only. It is not associated with a real brand or offer.

## Generated document fixtures

- `claim_40_percent.txt`, `.docx`, `.pdf`: same unsupported 40% anchor claim in the three document formats.
- `claim_28_percent.txt`: positive near-pair supported by the scoped synthetic fact.
- `expired_20_percent.txt`: evidence that expired before the default review time.
- `future_25_percent.txt`: fact that is not yet effective at the default review time.
- `conflicting_29_percent.txt`: isolated equal-authority conflict case.
- `absent_evidence_72_hours.txt`: claim intentionally missing approved evidence.
- `terminology_variant.txt`: non-canonical product name.
- `unsupported_tone.txt`: unapproved superlative and guarantee language.
- `malformed.pdf`: invalid PDF structure for intake rejection.
- `oversized_upload.txt`: 1.5 MB fixture for configurable size-limit tests.

## Generated image fixtures

- `social_unsupported_claim.png` and `.jpg`: wrong numeric claim, non-approved logo variant and low-contrast fine print.
- `social_supported_clean.png`: supported 28% claim, approved synthetic logo and readable fine print.
- `social_low_confidence_ocr.png`: blurred/low-resolution version for OCR uncertainty tests.

Run `python scripts/generate_demo_fixtures.py` to regenerate the files. Dependencies for this helper are listed in `scripts/requirements-fixtures.txt`. The script also updates `fixtures/fixture_manifest.json` with SHA-256 hashes and expected case labels.

The PDF fixture's extraction coordinates are approximate and must be validated by the parser implementation before they are used as golden region coordinates. OCR confidence thresholds and visual similarity thresholds must be evaluated, not guessed from the fixture itself.
