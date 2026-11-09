# Build 016 — Phase 04 completion notes

Build 016 completes the Phase 04 implementation scope for the Brand Control Center and Knowledge Pack lifecycle.

## Changes

- Added guided owner creation forms for facts, policies, terminology and voice examples. The advanced JSON editor remains available for careful edits.
- Enforced exact approved-source ID/version/quote traceability for new factual records and policy clauses. Policy provenance is server-controlled and cannot be weakened by client-supplied JSON.
- Required uploaded PDF/DOCX sources to have a clean malware scan and completed extraction before they can substantiate an approved policy clause.
- Expanded Knowledge Pack conflict validation across overlapping facts, policy clauses, locale-aware terminology and voice guidance; conflicts are returned for owner resolution rather than silently ranked.
- Added Brand Control Center search and filters for product/offer, channel, locale, geography, audience, owner/approver and validity state.
- Added a guarded source replacement lifecycle. Previous source versions remain intact until replacements scan cleanly and extraction completes.
- Added a bounded source-version comparison API/UI with private storage references redacted.
- Added safe source deletion for unapproved, unreferenced draft-only sources; deletion is blocked when facts, immutable published versions or other drafts depend on the source. Deleting a removable latest version restores its predecessor's prior state.
- Added an integration test for competing PostgreSQL publish attempts. It requires exactly one successful immutable version publication.
- Added CI jobs for a non-superuser PostgreSQL RLS/concurrency run, a live ClamAV test and frontend npm lint/typecheck/build.

## Verification

- `pytest -o addopts='' -q -ra`: **132 passed, 2 skipped, 0 failed**. Both skips are PostgreSQL-only: RLS enforcement and concurrent publication.
- `python -m compileall -q backend apps migrations tests scripts`: passed.
- `python -m alembic upgrade head`: passed; local SQLite is at `20261109_0005`.
- `python scripts/verify_database.py`: all 16 required tables present.
- `python scripts/evaluate_golden_cases.py`: **11 PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL**.
- TypeScript compiler API syntax parsing passed for `apps/web/app/brand/page.tsx` and `apps/web/components/knowledge-record-forms.tsx`.
- CI YAML parsed with four jobs: backend, backend-postgres, clamav-live and frontend.

## Not verified in this environment

- Hosted PostgreSQL RLS and the concurrent publication assertion were not executed locally; the two PostgreSQL-only tests are skipped under SQLite.
- No Docker/psql binaries or live ClamAV daemon were available.
- `npm run lint` failed to start because the local project executable `eslint` is missing. Full npm install, typecheck and production build are not claimed.
- CI job definitions are not proof of successful CI runs. Record hosted results in `docs/phase-gates/PHASE-04-STATUS.md` when observed.

## Upgrade from Build 015

Back up the current repository, `.env`, `data/` and database. Extract Build 016 over the source tree and preserve `.env`, `.git`, `.venv`, `node_modules` and local runtime `data/`. Then run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python scripts/verify_database.py
pytest -q
python scripts/evaluate_golden_cases.py
```

Migration head remains `20261109_0005`; no new database migration was necessary for this phase-completion patch.
