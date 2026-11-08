# Verification record — current MVP

**Recorded:** 2026-11-08. Participant-provided Windows frontend output and an independently executed clean local HTTP smoke run are included below. Re-run all commands on the final submission checkout and update this record if results differ.

## Automated results in the working environment

| Check | Result | Notes |
|---|---|---|
| `pytest -q` | **27 passed** | Unit and API integration tests, including creator ownership and image manual-review approval path |
| `python scripts/evaluate_golden_cases.py` | **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** | 12 synthetic ORBITA cases; manual item covers automated logo identity/contrast which is intentionally not implemented |
| `python -m compileall -q backend apps tests scripts` | **Passed** | Python syntax compilation |
| Clean SQLite `alembic upgrade head` | **Passed** | Empty database `data/migration_verify.db` |
| `alembic check` | **No new upgrade operations detected** | Models matched current initial migration in the tested environment |
| `npm install` | **Passed on participant Windows machine** | Participant reports 433 packages added; 8 moderate audit findings were shown. Do not run `npm audit fix --force` without reviewing changes. Retain the generated `package-lock.json`. |
| `npm run lint` | **Passed on participant Windows machine** | ESLint completed with no errors or warnings in the supplied terminal output |
| `npm run typecheck` | **Passed on participant Windows machine** | `tsc --noEmit` completed with no diagnostics |
| `npm run build` | **Passed on participant Windows machine** | Next.js 16.4.5 production build compiled, typechecked and generated all 8 pages |
| `python scripts/smoke_vertical_slice.py` | **8 checks passed** | Live HTTP smoke against a clean local SQLite API instance; confirms upload → contradicted evidence → approval block → hash-bound patch → v2 → supported claim → reviewer approval → history/audit |

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
npm run typecheck
npm run build
```

The participant has supplied successful output for all three frontend commands. Preserve the corresponding `package-lock.json` from the participant checkout.
