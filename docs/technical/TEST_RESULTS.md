# Verification record — current MVP

**Recorded:** 2026-11-08. Re-run all commands on the submission machine and update this record if results differ.

## Automated results in the working environment

| Check | Result | Notes |
|---|---|---|
| `pytest -q` | **27 passed** | Unit and API integration tests, including creator ownership and image manual-review approval path |
| `python scripts/evaluate_golden_cases.py` | **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** | 12 synthetic ORBITA cases; manual item covers automated logo identity/contrast which is intentionally not implemented |
| `python -m compileall -q backend apps tests scripts` | **Passed** | Python syntax compilation |
| Clean SQLite `alembic upgrade head` | **Passed** | Empty database `data/migration_verify.db` |
| `alembic check` | **No new upgrade operations detected** | Models matched current initial migration in the tested environment |
| `npm install` | **Timed out in this environment** | No `package-lock.json` was generated here |
| TypeScript `transpileModule` syntax check | **14 files, 0 syntax diagnostics** | Checks TS/TSX parsing/transpilation only; does not resolve imports or validate React/Next types |
| `tsc --noEmit` | **Not verified** | Frontend dependencies and type declarations are not installed; this is not a successful typecheck |
| `npm run build` | **Not run / not verified** | Run after dependency install on the participant machine |

## Golden evaluation interpretation

- 11 cases automatically passed against the expected deterministic rules.
- 1 case requires manual inspection of visual logo identity and contrast.
- 0 cases failed.
- The corpus is synthetic and narrow. It does not estimate accuracy on arbitrary company content and is not a legal, accessibility or brand certification.

## Final local verification commands

```powershell
pytest
python scripts/evaluate_golden_cases.py
python -m compileall -q backend apps tests scripts
python -m alembic upgrade head
```

In `apps/web`:

```powershell
npm install
npm run lint
npm run build
```

Only record those frontend checks as passed after they complete successfully.
