# API surface — implemented MVP

Base path: `/api/v1`

| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/login` | Obtain a bearer token; requires explicit brand/workspace choice if the account has multiple active memberships |
| GET | `/auth/me` | Current user identity and selected membership role/context |
| GET | `/auth/workspaces` | List the caller's active workspace/brand memberships |
| POST | `/auth/switch-context` | Revoke the current session and issue a new session bound to another active membership |
| POST | `/auth/logout` | Revoke the current server-side session |
| GET | `/workspace/memberships` | List memberships for the selected brand (Brand Owner / Administrator) |
| POST | `/workspace/memberships` | Add an existing account to the selected brand (Brand Owner / Administrator with role-grant limits) |
| PATCH | `/workspace/memberships/{membership_id}` | Change role or activation status (Administrator only; last active administrator protected) |
| GET | `/brands/current` | Current active tenant Brand Knowledge Pack metadata and fingerprint |
| GET | `/brands/current/management` | Read-only active pack snapshot and published version history (Brand Owner, Reviewer, Administrator) |
| GET | `/brands/current/versions` | Published Knowledge Pack versions |
| POST | `/brands/current/drafts` | Create a Brand Owner draft from the current active version |
| GET | `/brands/current/drafts/{draft_id}` | Read a Brand Owner's draft |
| PUT | `/brands/current/drafts/{draft_id}/section` | Replace one typed JSON section in a draft |
| POST | `/brands/current/drafts/{draft_id}/validate` | Validate draft structure and record identifiers |
| POST | `/brands/current/drafts/{draft_id}/publish` | Publish a new immutable pack version (Brand Owner only) |
| POST | `/brands/current/drafts/{draft_id}/sources` | Register source provenance in the draft; URL metadata is not fetched |
| POST | `/brands/current/drafts/{draft_id}/records/{record_type}/{record_id}/decision` | Brand Owner approve/reject/draft/not_approved a fact, policy, term, source or asset |
| POST | `/brands/current/drafts/{draft_id}/assets` | Upload a bounded PNG/JPEG/WebP asset into private object storage as a draft |
| GET | `/brands/current/drafts/{draft_id}/assets/{asset_id}` | Preview an uploaded draft asset with hash verification (Brand Owner only) |
| GET | `/brands/current/assets/{asset_id}` | Retrieve an approved published asset in the selected brand, with hash verification |
| GET | `/dashboard/summary` | Workspace/creator summary |
| GET | `/submissions` | List visible submissions |
| POST | `/submissions` | Upload initial source and run checks |
| GET | `/submissions/{id}` | Get current submission version/review |
| POST | `/submissions/{id}/revisions/upload` | Upload a new immutable source version |
| POST | `/submissions/{id}/revisions` | Create a TXT-only revision from text payload |
| GET | `/reviews/{id}` | Fetch review by review ID or submission ID |
| POST | `/reviews/{id}/findings/{finding_id}/resolve` | Reviewer resolution note (multipart form field `reason`) |
| POST | `/reviews/{id}/patches` | Propose a hash-bound local text patch |
| POST | `/patches/{id}/accept` | Accept TXT patch as a new version and re-run review |
| POST | `/reviews/{id}/decisions` | Approve, request changes, reject or authorised override |
| GET | `/content-versions/{id}/download` | Retrieve original source for an authorised user |
| POST | `/content-versions/{id}/grant` | Create a short-lived download grant bound to the current user/session/membership/version |
| GET | `/content-grants/{grant_token}` | Redeem a signed, expiring original-file grant; issuing session/membership must remain active |
| GET | `/audit` | Recent audit records visible to current role and brand context |

Health routes: `/health/live`, `/health/ready`.

All routes other than login, health and the signed file-grant redemption route require a bearer token. The grant route validates its signed token and live server-side session/membership. Role authority is read from the selected persisted brand membership on every request; legacy JWT role/tenant claims and the legacy global user role are not authorization sources. Creator and Agency access is restricted to the member's own submissions. Reviewer, Brand Owner and Administrator access is scoped to the selected tenant and brand. Brand Owners may add creator, agency and reviewer memberships; only Administrators may grant elevated roles, change membership roles or activate/deactivate memberships. The last active Administrator cannot be demoted or deactivated. Workspace switching revokes the old session. PostgreSQL RLS supplies a database defence layer on workspace and derived-content tables; the hosted non-superuser PostgreSQL CI result remains pending.

Errors use stable detail codes where defined, including `INVALID_UPLOAD`, `UPLOAD_TOO_LARGE`, `TIMEZONE_REQUIRED`, `PARSE_FAILED`, `OPEN_BLOCKING_FINDINGS`, `STALE_VERSION`, `PATCH_NOT_LOCAL` and `FORMAT_REQUIRES_EXTERNAL_EDIT`.

### Workspace and identity semantics (Build 011)

- `/auth/login` accepts optional `brand_id` (the selected membership's `brand_record_id`). When the account has multiple active memberships and no selection is provided, it returns `409 WORKSPACE_SELECTION_REQUIRED` with available membership summaries.
- `/auth/switch-context` accepts the selected membership's `brand_record_id`, revokes the current session and issues a new token. Use `POST /auth/logout` to revoke a session explicitly.
- `/workspace/memberships` lists selected-brand memberships. A Brand Owner may add `creator`, `agency` or `reviewer`; an Administrator may add any defined role. `/workspace/memberships/{membership_id}` is Administrator-only and protects the last active Administrator.
- The file grant is a signed bearer link, expiring after `FILE_GRANT_MINUTES` (default 5; maximum 15). It is tied to the issuing session and membership; logout, session expiry, or membership deactivation invalidates it.


### Brand Knowledge Pack semantics (Build 012)

- Knowledge Pack directories and drafts are scoped by both tenant ID and selected brand ID. New non-demo brands begin with empty facts, policies, terms, assets and sources; the legacy tenant-only demo pack is migrated only into the original ORBITA brand namespace.
- Source registration preserves source ID/type/version, owner, approval state, validity and reference excerpt/URI metadata. Remote URLs are never fetched automatically. A source marked approved in a draft is not authoritative until the whole pack is validated and published.
- Record decisions support fact, policy, terminology, source and uploaded asset records. Decision reasons are retained in the draft and publication audit.
- Uploaded assets are PNG/JPEG/WebP only. SVG is rejected by the new upload route. Approved uploaded assets are re-hashed during draft validation and again when served. This is not malware scanning or automated visual identity certification.
- The pack metadata store remains filesystem-backed and single-host. Multi-process/distributed publication locking and PostgreSQL-backed pack metadata remain future work.
