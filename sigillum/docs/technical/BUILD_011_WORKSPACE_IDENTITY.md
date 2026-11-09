# Build 011 — workspace identity, memberships and access boundaries

**Date:** 2026-11-09  
**Base:** Build 010 (all prior builds retained)  
**Phase:** 03 — Identity, workspace boundaries and permissions  
**Gate:** Phase 03 remains **PARTIALLY COMPLETE / IN PROGRESS** until PostgreSQL RLS CI and Build 011 frontend gates are verified.

## Product/security contract

A user account is not itself a workspace permission. The selected active `Membership` is the authorization source and binds the actor to one tenant, one brand and one role. A single account may have several memberships. Every request re-reads the server-side session and membership; JWT role/tenant claims are informational only. Unknown, inactive, revoked, expired or mismatched context fails closed.

## Implemented

- Added persisted `Tenant`, `Brand`, `Membership` and `UserSession` records.
- Added forward-only Alembic migration `20261109_0003_workspace_identity.py`; the old migration revisions are unchanged.
- Migration backfills existing users into the legacy single-brand tenant without changing their effective one-brand access. When a legacy tenant already has multiple brands, the migration grants only brands evidenced by the user's own submissions or attributed content actions; users with no attributable scope receive no membership by default.
- Added multi-membership login selection, `/auth/workspaces`, `/auth/switch-context` and server-side logout revocation.
- Added per-request active membership, tenant, brand and user-session checks. The server does not trust the role/tenant claims in a decoded access token for authorization.
- Added creator/agency own-content restrictions and tenant+brand filters for submissions, dashboard counts and audit history.
- Added Brand Owner / Administrator member listing and constrained member creation. Brand Owners may add creator/agency/reviewer memberships; Administrators can add all defined roles and update activation/roles. Last active administrator protection covers role-only demotion as well as deactivation.
- Added a usable workspace selector to the application shell and a Workspace Access UI for the allowed roles. The UI explicitly describes that account invitations/creation are not implemented and the account must already exist.
- Added short-lived file-grant tokens bound to user ID, session ID, membership ID, tenant, brand, brand record and content version. The API checks that the underlying session and membership remain active before returning a hash-verified original.
- Added PostgreSQL `ENABLE` + `FORCE ROW LEVEL SECURITY` policies for tenants, brands, memberships, user sessions, submissions, content versions, reviews, findings, patches, decisions and audit events. Application transaction-local GUC scope is reapplied after transaction boundaries. Membership access uses separate SELECT / INSERT / UPDATE policies: self-read is allowed, Brand Owners may insert contributor-level memberships only, Administrators may manage memberships in the selected brand, and direct membership deletion has no policy (default deny).
- Membership mutations lock the selected brand row in PostgreSQL so concurrent role/deactivation requests cannot both pass the last-active-administrator check based on stale counts.
- Added `scripts/verify_database.py` checks for RLS enable/force/policy presence when running against PostgreSQL, including the three command-specific membership policies.
- Demo bootstrap refreshes its database scope with the internal Brand primary key before membership insertion, matching the membership RLS policy.
- Membership mutations lock the selected Brand row so concurrent changes cannot both pass the last-active-administrator check using stale counts.
- PostgreSQL CI uses a non-superuser, `NOBYPASSRLS` application database role; this is important because superuser sessions bypass normal RLS policy enforcement.

## Verification evidence

- SQLite backend suite: **84 passed, 1 skipped**. The single skip is the PostgreSQL-only RLS integration check.
- `python -m compileall -q backend apps migrations tests scripts`: passed.
- Fresh SQLite migration reached `20261109_0003`; all 12 mapped tables were present.
- A copy of the Build 010 database upgraded from `20261109_0002` to `20261109_0003`; `scripts/verify_database.py` reported current migration and no missing tables.
- Multi-brand legacy migration fixture: user with historical submissions in two brands received only those two evidenced memberships; reviewer with action history in one brand received only that brand; an unassociated account received zero memberships.
- Synthetic golden set: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL**.
- API integration coverage includes multi-membership selection, context switch, old-token revocation, logout revocation, membership deactivation, role source-of-truth, cross-tenant access denial, short-lived file grants and logout invalidation, admin membership management, owner role limits, last-admin protection and Agency own-submission restriction.
- PostgreSQL is not running in this authoring environment. The PostgreSQL-only test is present and is expected to execute in the `backend-postgres` CI job; the hosted result has not yet been observed. The RLS SQL is therefore configured and statically/migration-reviewed but not claimed as live PostgreSQL-verified.
- `npm ci` timed out in this authoring environment. Build 011 frontend lint, TypeScript and production build remain pending. The participant's prior Windows success applied to the pre-Build-011 frontend only.

## Role and access matrix

| Role | Content access | Workspace member actions | Brand Knowledge Pack |
|---|---|---|---|
| Creator | Own submissions in selected brand | None | No mutation |
| Agency | Own submissions in selected brand | None | No mutation |
| Reviewer | Selected brand review work | None | Read only |
| Brand Owner | Selected brand workspace | Add creator/agency/reviewer only | Draft, validate and publish |
| Administrator | Selected brand workspace | Add all roles; change role/active state; cannot remove last admin | Read only |

Administrator privilege does not imply Brand Owner policy mutation. Brand Owner privilege does not imply Administrator control.

## Remaining / deferred

- Observe hosted PostgreSQL 17 + pgvector CI using the non-superuser role and confirm every RLS test and verifier passes.
- Re-run frontend lint, typecheck and production build on Build 011.
- Account invitations/activation emails, password reset, MFA, SSO and enterprise identity remain deferred.
- The Knowledge Pack store remains filesystem-backed and currently keyed by tenant, so the current event demo is still seeded as one brand per workspace. Full multi-brand Knowledge Pack store partitioning is a later requirement before enabling multiple live brands inside one tenant.
- Additional RLS policies may be required when knowledge chunks, embeddings, durable jobs, exports and worker-owned tables move into PostgreSQL; they are not all persisted database entities yet.

## Commands

```powershell
python -m pip install -e "[dev]"
python -m alembic upgrade head
python scripts/verify_database.py
pytest -q
python scripts/evaluate_golden_cases.py
python -m compileall -q backend apps migrations tests scripts
```

For frontend validation from `apps/web`:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```
