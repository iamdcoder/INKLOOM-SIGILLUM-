# Verification record — current MVP

**Latest update:** 2026-11-09, Build 015. Older entries below are retained as historical checkpoints; current results are summarised first.


## Build 015 — asset usage policies and intended-use context

| Check | Result | Notes |
|---|---|---|
| `python -m pytest -q -rA` | **119 passed, 1 skipped, 0 failed (120 collected)** | SQLite/local suite; the skipped test exercises PostgreSQL RLS only. |
| Python `compileall` | **Passed** | Backend, apps, migrations, tests and scripts. |
| `python scripts/verify_database.py` | **Passed** | SQLite at `20261109_0005`; all 16 required tables present; no missing tables. |
| Golden evaluation | **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** | Twelve deterministic synthetic cases; visual logo/contrast case remains manual. |
| TypeScript syntax parsing | **Passed** | Four changed TS/TSX files parsed by the TypeScript compiler API. This is not a project typecheck. |
| `npm ci` | **Timed out** | No project-local Next/ESLint/TypeScript binaries were available afterward. |
| Frontend lint/typecheck/build | **Not verified** | Must be run on a working dependency installation. |
| Live PostgreSQL, ClamAV, MinIO, browser E2E | **Not run** | Not claimed as verified. |

Build 015 adds owner-authored asset use policy configuration, measured palette and dimension validation, controlled submission intended use, exact-SHA-256-match review-time policy checks, and migration `20261109_0005`. See `docs/technical/BUILD_015_ASSET_USAGE_POLICIES.md`.

## Build 010 — database lifecycle

| Check | Result | Notes |
|---|---|---|
| `python -m pytest` | **72 passed** | SQLite/local authoring environment; includes six database lifecycle tests |
| Fresh SQLite Alembic migration | **Passed** | Upgrade empty database to head, verify all eight mapped tables, repeat upgrade at head |
| Migration readiness | **Passed** | Pending schema is detected; migrated schema reports current revision `20261109_0002` |
| `python scripts/verify_database.py` | **Passed** | Local SQLite schema at `20261109_0002`; eight required tables present |
| SQLite FK enforcement | **Passed** | Invalid foreign-key insert raises `IntegrityError` |
| PostgreSQL URL normalisation | **Passed** | `postgresql://` is normalised to the pinned `postgresql+psycopg` driver name |
| Python compilation | **Passed** | `python -m compileall -q backend apps tests scripts` |
| CI workflow YAML | **Parsed successfully** | Includes independent PostgreSQL 17 + pgvector service-backed job |
| PostgreSQL server/driver test in authoring runtime | **Not run** | No local PostgreSQL server and no `psycopg` package in this authoring runtime; the configured hosted CI job must be observed passing |
| Live MinIO/AWS | **Not run** | Build 009 S3 adapter still has offline fake-client coverage only |
| Golden evaluation | **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** | Same 12 synthetic ORBITA cases; manual visual case remains a deliberate handoff |

The PostgreSQL CI job is configured but not claimed as passed until GitHub Actions executes it. Frontend files were not changed in Build 010, so the participant-confirmed 2026-11-08 Windows lint/typecheck/build results remain the latest frontend evidence.


**Recorded:** 2026-11-08. Participant-provided Windows frontend output and an independently executed clean local HTTP smoke run are included below. Re-run all commands on the final submission checkout and update this record if results differ.

## Automated results in the working environment

| Check | Result | Notes |
|---|---|---|
| `python -m pytest tests -q` | **50 passed** | Build 008 unit and API integration tests, including temporal retrieval, source precedence and Brand Owner lifecycle |
| `python scripts/evaluate_golden_cases.py` | **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** | 12 synthetic ORBITA cases; manual item covers automated logo identity/contrast which is intentionally not implemented |
| `python -m compileall -q backend tests` | **Passed** | Python syntax compilation |
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


## Build 006 visual evidence verification

- Backend suite: **33 passed** (unit + integration).
- Image extraction contract: image metadata, decoded-pixel SHA-256, palette inventory, OCR line IDs, polygon coordinates and normalized bounding boxes are tested.
- Contrast estimator: low-contrast candidate (`FAIL`) and missing approved threshold (`UNMEASURABLE`) are covered by deterministic tests.
- Scope guard: structured threshold is applied only to channels covered by the approved synthetic policy.
- Integration: image upload returns region geometry through the existing review API; out-of-scope contrast policy does not create a contrast finding.
- Frontend: the changed TSX file passes TypeScript syntax transpilation. Full ESLint, project typecheck and Next.js production build must be rerun on the developer machine because this packaging environment does not contain the project's installed npm dependencies.

The image contrast value is a local segmentation estimate, not a complete accessibility audit. Human confirmation remains mandatory.


## Build 007 verification (2026-11-08)

- `python -m compileall -q backend/sigillum apps tests scripts`: passed.
- `python -m pytest tests -q`: **40 passed**.
- New Knowledge Pack tests cover immutable version publication, duplicate-ID validation, stale-draft protection, cross-platform asset-path traversal rejection, Brand Owner authorization, publication audit events and preservation of historical review fingerprints.
- Frontend TSX syntax transpilation: zero syntax diagnostics. Full Next.js lint/typecheck/production build must be rerun on the participant Windows environment after applying the patch.

## Build 008 — temporal truth and retrieval (2026-11-08)

- `python -m pytest tests -q`: **50 passed**.
- `python -m compileall -q backend tests`: passed.
- `python scripts/evaluate_golden_cases.py`: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**.
- `python scripts/smoke_vertical_slice.py` against a fresh isolated SQLite-backed local API: **8/8 checks passed**; report retained at `reports/build008_live_smoke_verification.json`.
- New tests cover valid-time versus record-time separation, not-yet-recorded facts, no-longer-recorded facts, invalid time intervals, approved-only retrieval, fail-closed missing scope, deterministic RRF trace, evidence provenance and source precedence.
- Workbench TSX syntax transpilation: to be checked in the packaging environment; participant must run `npm run lint`, `npm run typecheck`, and `npm run build` on Windows after applying Build 008.
- No database migration was added. Current pack source and retrieval remain local filesystem/JSON adapters.
