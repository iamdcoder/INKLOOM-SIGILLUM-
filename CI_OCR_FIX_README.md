# Sigillum CI OCR dependency fix

## Why CI failed

The backend test `test_image_review_requires_visual_inspection_before_human_approval` exercises real image OCR and asserts that extraction confidence is at least `0.75` for the clean synthetic PNG. `pytesseract` is only a Python wrapper; it does not install the native Tesseract executable or its trained language data.

The local Windows environment has Tesseract installed, so the test passes locally. The GitHub Actions `ubuntu-latest` runner did not install Tesseract, so the OCR adapter returned a partial extraction with confidence `0.0` and the test failed.

## Patch

Replace `.github/workflows/ci.yml` with the file at the same path in this patch. The backend CI job now:

1. Installs `tesseract-ocr` and `tesseract-ocr-eng` using Ubuntu's package manager.
2. Sets `TESSERACT_CMD=/usr/bin/tesseract` explicitly.
3. Verifies the executable and English trained data before running Python tests.
4. Runs the existing backend tests and golden evaluation unchanged.

The test assertion is deliberately not weakened. A CI run without a functioning OCR engine should fail rather than silently report success.

## Apply

Extract this patch into the repository root, preserving the `.github/workflows/ci.yml` path, or replace that file manually.

## Verify

Push a new commit (or rerun the failed workflow) and inspect the `backend` job. It should show a `Verify Tesseract and English language data` step before dependency installation and pytest.

This patch does not change application code, test expectations, or frontend dependencies.
