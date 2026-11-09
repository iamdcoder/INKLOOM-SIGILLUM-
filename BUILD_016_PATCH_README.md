# Inkloom Sigillum — Build 016 patch handoff

**Build:** 016 (cumulative, based on Build 015)  
**Phase:** 04 — Brand Control Center and Knowledge Pack lifecycle  
**Phase implementation status:** Complete. External operational checks remain pending; see `docs/phase-gates/PHASE-04-STATUS.md`.

## Main implementation

1. Guided owner creation forms for facts, policy clauses, terminology and voice examples.
2. Exact approved-source/version/quote provenance for new facts and policy clauses. The server owns the policy-provenance guard; a generic JSON edit cannot remove it.
3. Broader scope/validity conflict validation for facts, policies, terminology and voice guidance.
4. Brand Control Center search and filters for product/offer, channel, locale, geography, audience, owner/approver and validity.
5. Safe source v1→v2 replacement: old source remains until the replacement has a CLEAN scan and complete extraction.
6. Bounded source-version comparison with private object-storage keys redacted.
7. Safe deletion for unapproved, unreferenced draft sources only; protected history and predecessor restoration.
8. CI coverage configured for live PostgreSQL RLS/concurrency, ClamAV and frontend lint/typecheck/build.

## Verification performed

- Backend/unit/integration: **132 passed, 2 skipped, 0 failed (134 collected)**.
- The skipped tests are intentionally PostgreSQL-only (RLS and concurrent publication).
- Python compilation passed.
- Alembic migration is current at `20261109_0005`; all 16 required local SQLite tables are present.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**.
- TypeScript syntax parsing passed for the two changed Knowledge Pack TSX files.
- CI YAML parsed with all four expected jobs.

## Known environment limits

- PostgreSQL RLS and concurrent publish must be verified in the configured non-superuser PostgreSQL CI job. They were not run in local SQLite.
- Live ClamAV was not run locally; the `clamav-live` CI job is configured.
- Full frontend lint/typecheck/build are not verified. Local `npm run lint` could not find the project-local ESLint executable (`eslint: not found`). The `frontend` CI job is configured but has not been observed passing.
- Do not describe CI job configuration as a passing result.

## Upgrade from Build 015 — Windows PowerShell

Back up the project, `.env`, database and local `data/` first. Extract Build 016 over the source tree. Preserve `.env`, `.git`, `.venv`, `node_modules`, `data/` and any local database/private uploads.

```powershell
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python scripts/verify_database.py
pytest -q
python scripts/evaluate_golden_cases.py
```

## Scope limitations

- URI sources are not fetched; they remain provenance metadata.
- Palette rules are bounded RGB estimates, clear-space is manual review, and exact-hash asset checks do not identify logos embedded in other flattened creatives.
- Automated Impact Radar remains Phase 14 work.
- Automated TTL retention and storage-orphan reconciliation remain operational hardening.

See `docs/technical/BUILD_016_PHASE04_COMPLETION.md` and `docs/phase-gates/PHASE-04-STATUS.md` for full detail.
