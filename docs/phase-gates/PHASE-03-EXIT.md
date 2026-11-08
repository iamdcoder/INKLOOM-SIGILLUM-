# Phase 03 — Exit evidence

**Decision:** NOT SIGNED OFF — partial implementation only.  
**Build:** 011  
**Date:** 2026-11-09

## Acceptance review

| Exit condition | Result | Evidence |
|---|---|---|
| Persisted identity and membership model | PASS (SQLite) | `Tenant`, `Brand`, `Membership`, `UserSession`; migration revision `20261109_0003` |
| Server-side role and permission matrix | PASS (API integration) | Role from active membership; creator/agency own-content restriction; role-gated membership APIs |
| Tenant/brand scope at API and object boundaries | PASS (API integration) | Context-bound actor, selected brand filters, session-bound file grants |
| Session expiry, logout, workspace-switch revocation | PASS (API integration) | `test_session_is_server_revocable_and_logout_invalidates_token`, context-switch tests, file grant invalidation |
| Existing Build 010 DB upgrade | PASS (SQLite) | Upgraded copied Build 010 DB from `20261109_0002` to `20261109_0003`; verifier found no missing tables |
| Multi-brand backfill defaults to least privilege | PASS (SQLite fixture) | Existing creator only receives historically evidenced brands; unassociated user receives zero memberships |
| PostgreSQL RLS policies are installed and forced | IMPLEMENTED, NOT LIVE VERIFIED | Migration code and non-superuser CI job; no local PostgreSQL service available |
| Cross-tenant database RLS negative tests | PENDING HOSTED CI | PostgreSQL-only test is present and skipped under SQLite |
| Build 011 frontend lint/typecheck/build | PENDING | `npm ci` timed out in authoring environment |

## Current result

**Phase 03 remains PARTIALLY COMPLETE.** SQLite/API-level identity and membership functionality is verified. PostgreSQL RLS runtime behaviour and the revised frontend are not yet verified. This exit document must only be changed to SIGNED OFF after those pending checks have actually passed.

## Required evidence to append after external checks

- GitHub Actions workflow URL and run ID for the `backend-postgres` job.
- `scripts/verify_database.py` JSON output showing `row_level_security.status = "enforced"` for all protected tables.
- PostgreSQL suite summary including the RLS unscoped and cross-brand read test.
- Windows or CI outputs for `npm run lint`, `npm run typecheck`, `npm run build` on Build 011.
