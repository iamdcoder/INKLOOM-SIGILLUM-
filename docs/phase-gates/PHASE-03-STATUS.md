# Phase 03 — Identity, workspace boundaries and permissions

**Current status:** PARTIALLY COMPLETE — PostgreSQL and frontend exit evidence pending.  
**Implementation baseline:** Build 011, cumulative from Build 010.

## Phase objective

Establish trustworthy access control before introducing more sensitive brand and content data.

## Requirement status

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Authentication adapter / demo login | Implemented | Password verification, signed access token, server-side session row |
| Tenant/workspace model | Implemented | `Tenant` table, tenant scoped on each membership |
| Brand membership model | Implemented | `Brand` and `Membership` tables; multiple memberships per account supported |
| Role definitions independent of frontend | Implemented | Role is read from active DB membership on every request; JWT role is informational |
| Session expiry and logout | Implemented | `UserSession.expires_at`, `revoked_at`, logout and context-switch revocation |
| Membership activation/deactivation | Implemented | Admin API and Workspace Access UI; deactivation invalidates existing session |
| Selected brand scope in API routes | Implemented | `CurrentActor` binds tenant, brand and membership; resource checks before return |
| Storage grants scoped to context | Implemented | Short-lived signed grant bound to session/membership/tenant/brand/version |
| Central default-deny authorization | Implemented | Active membership validation, role dependencies, object scope checks |
| PostgreSQL RLS | Implemented in migration | `ENABLE` + `FORCE` on 11 tables; memberships use SELECT/INSERT/UPDATE command-specific policies; live PostgreSQL CI not yet observed |
| Cross-tenant and cross-brand negative tests | Implemented | SQLite API test coverage; PostgreSQL-specific RLS test executes in hosted job only |
| Workspace switch UI | Implemented | Login selection and sidebar context selector; Build 012 frontend gates pending |
| Membership management UI | Implemented | Brand Owner / Administrator page; only existing accounts can be added |
| Enterprise SSO / invitations / MFA | Deferred | Not required for the synthetic demo path; future enhancement |

## Verification record

- Backend suite: **84 passed, 1 skipped** under SQLite. The one skip is the PostgreSQL-only RLS test.
- Fresh database migrated to `20261109_0003`; `scripts/verify_database.py` reported all 12 required tables.
- A real Build 010 database copy upgraded from `20261109_0002` to `20261109_0003` without manual edits.
- Multi-brand migration fixture confirmed least-privilege backfill: existing user received only brands supported by their historical authored content; a user with no attributable record received no membership.
- `python -m compileall` passed.
- Golden evaluation: 11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL.
- PostgreSQL/RLS test is configured in CI but was not run locally because no PostgreSQL service is available here.
- `npm ci` timed out in this authoring environment. Participant must run frontend lint, typecheck and production build on Build 012; the current authoring check syntax-transpiled 15 TypeScript/TSX files with zero diagnostics, but that is not a full project typecheck or build.

## Gate decision

**Phase 03 is not yet signed off.** Do not describe PostgreSQL multi-tenant isolation as production verified until the non-superuser PostgreSQL CI job passes and the latest Build 012 frontend checks pass. Build 012 subsequently closes the tenant-only Knowledge Pack namespace gap by partitioning pack metadata/drafts by tenant and brand and ensuring non-demo brands start with empty packs. This is verified in the Phase 04 brand-isolation tests. The remaining Phase 03 external gates—live PostgreSQL RLS execution and complete frontend lint/typecheck/build—are still unresolved.

## Next action

Run the `backend-postgres` GitHub Actions job and all three frontend quality gates. If they pass, record their exact run IDs/outputs in this file and `docs/phase-gates/PHASE-03-EXIT.md`; do not infer success from the job definition alone.
