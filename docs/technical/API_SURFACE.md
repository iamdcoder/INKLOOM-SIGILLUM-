# API surface — implemented MVP

Base path: `/api/v1`

| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/login` | Obtain a bearer token |
| GET | `/auth/me` | Current user identity and role |
| GET | `/brands/current` | Current active tenant Brand Knowledge Pack metadata and fingerprint |
| GET | `/brands/current/management` | Read-only active pack snapshot and published version history (Brand Owner, Reviewer, Administrator) |
| GET | `/brands/current/versions` | Published Knowledge Pack versions |
| POST | `/brands/current/drafts` | Create a Brand Owner draft from the current active version |
| GET | `/brands/current/drafts/{draft_id}` | Read a Brand Owner's draft |
| PUT | `/brands/current/drafts/{draft_id}/section` | Replace one typed JSON section in a draft |
| POST | `/brands/current/drafts/{draft_id}/validate` | Validate draft structure and record identifiers |
| POST | `/brands/current/drafts/{draft_id}/publish` | Publish a new immutable pack version (Brand Owner only) |
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
| GET | `/audit` | Recent audit records visible to current role |

Health routes: `/health/live`, `/health/ready`.

All routes other than login and health require a bearer token. Creator access is restricted to the creator's own submissions. Reviewer, brand-owner and administrator roles can inspect workspace content; decision and override permissions remain distinct. Knowledge Pack mutation/publication is restricted to the Brand Owner. Reviewer and Administrator pack inspection is read-only.

Errors use stable detail codes where defined, including `INVALID_UPLOAD`, `UPLOAD_TOO_LARGE`, `TIMEZONE_REQUIRED`, `PARSE_FAILED`, `OPEN_BLOCKING_FINDINGS`, `STALE_VERSION`, `PATCH_NOT_LOCAL` and `FORMAT_REQUIRES_EXTERNAL_EDIT`.
