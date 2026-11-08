# Live vertical-slice smoke test

**Status:** executed successfully against a clean local API process and temporary SQLite database on 2026-11-08.

The script `scripts/smoke_vertical_slice.py` exercises the API over HTTP rather than using FastAPI TestClient. It checks:

1. API readiness and database/storage availability.
2. Creator and reviewer authentication.
3. TXT upload and an immutable first content version.
4. A `CONTRADICTED` finding for `up to 40%`, including the exact content span and approved fact reference.
5. A reviewer approval attempt is blocked while the finding remains unresolved.
6. A hash-bound correction replaces `up to 40%` with the approved `up to 28%`.
7. The correction creates version 2 with a different SHA-256 and a fresh verification result of `SUPPORTED`.
8. A reviewer approves the exact version-2 hash; history and audit endpoints retain the lifecycle.

The observed run completed with `result: PASS`, `checks_passed: 8` and `submission_status: APPROVED`. The script creates a new synthetic demo submission on each run; it does not clean up or alter existing submissions.

This is live API integration evidence, not browser end-to-end evidence and not a production security certification.
