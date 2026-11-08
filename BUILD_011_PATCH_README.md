# Sigillum Build 011 — Phase 03 workspace identity and permissions

**Baseline:** Build 010, cumulative. This archive contains the full source snapshot; do not apply it as a small patch over an independently modified branch without reviewing differences.

## What this build adds

- Persisted `Tenant`, `Brand`, `Membership` and `UserSession` records.
- Alembic revision `20261109_0003`, with conditional table creation so it works both from an existing Build 010 database and from a fresh database where the legacy initial migration has already materialised current ORM metadata.
- Least-privilege legacy membership backfill. Single-brand legacy tenants preserve their existing scope. Multi-brand legacy users receive only memberships evidenced by their authored submissions or attributed actions; unassociated accounts receive no membership by default.
- Multi-workspace login selection, a sidebar workspace selector, server-side logout revocation and context-switch session replacement.
- Per-request checks of the user, session, membership, tenant and brand. Database membership role—not a stale role claim in the JWT—is authoritative.
- Creator and Agency own-submission restrictions, role-gated membership management, last-active-administrator protection and brand-row locking to serialize membership mutations.
- Five-minute default short-lived file grants (configurable from 1 to 15 minutes) bound to user, session, membership, tenant, brand and content version.
- PostgreSQL `ENABLE` + `FORCE ROW LEVEL SECURITY` for eleven tables. Membership uses separate SELECT, INSERT and UPDATE policies; direct DELETE remains default-deny.
- A non-superuser PostgreSQL CI job and a database verifier that checks RLS enabled/forced state and policy counts, including all three membership policies.
- Workspace Access UI for Brand Owners and Administrators, with existing-account-only membership creation.

## Apply this build

1. Back up the repository and database.
2. Extract this cumulative archive over the repository root.
3. Preserve `.env`, `.git`, `data/`, `.venv/` and `node_modules/`; they are intentionally excluded from the archive.
4. Activate the existing Python virtual environment and run:

```powershell
python -m pip install -e "[dev]"
python -m alembic upgrade head
python scripts/verify_database.py
pytest -q
python scripts/evaluate_golden_cases.py
python -m compileall -q backend apps migrations tests scripts
```

5. Re-authenticate once after applying Build 011. Build 010 sessions do not have the new server-side session/JWT identifier (`jti`) and are intentionally rejected.
6. From `apps/web`, run the frontend checks:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```

## Local evidence captured for this archive

- Backend suite: **84 passed, 1 skipped, 0 failed** under SQLite. The one skipped case is the PostgreSQL-only RLS runtime test.
- Python compilation: passed.
- Fresh SQLite database migrated to `20261109_0003`; all twelve mapped tables present.
- A copy of a Build 010 database migrated from `20261109_0002` to `20261109_0003`; existing user and membership backfill records were retained/created without manual SQL.
- Multi-brand fixture: the user with history in two brands received only those two brands; the reviewer with history in one brand received only that brand; an unassociated legacy account received zero memberships.
- Synthetic golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**.
- CI workflow YAML parsed successfully.
- Changed frontend TypeScript/TSX files passed syntax-only transpilation. This is not a full dependency-aware TypeScript check or Next.js build.

Detailed machine-readable evidence is in `reports/build011_validation.json`, `reports/build011_build010_upgrade.json`, `reports/build011_multibrand_backfill.json` and `reports/build011_sqlite_database_verification.json`.

## Important limitations / gates not claimed as passed

- PostgreSQL 17 + pgvector is configured in GitHub Actions, but no PostgreSQL service was available in the authoring environment. The hosted non-superuser RLS test and RLS verifier must pass before claiming database-enforced multi-tenant isolation is verified.
- `npm ci` timed out in the authoring environment. Build 011's frontend lint, full typecheck and production build remain unverified and must be run after extraction.
- The Knowledge Pack store is still filesystem-backed and tenant-keyed. It is not yet safe to enable multiple independently managed brands within one tenant.
- Workspace Access can add existing accounts; invitations, registration, password reset, MFA and SSO are not implemented.
- PostgreSQL RLS policies for future knowledge chunks, embeddings, durable jobs and exports must be added when those data classes become persisted database entities.
- Phase 03 is **PARTIALLY COMPLETE**, not signed off. See `docs/phase-gates/PHASE-03-EXIT.md`.

This build includes significant ChatGPT coding, debugging and documentation assistance. The participant must review and understand the implementation and disclose contributions accurately under the event rules.
