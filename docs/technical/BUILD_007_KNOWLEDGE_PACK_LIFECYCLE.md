# Build 007 — Brand Control Center and Knowledge Pack lifecycle

## Delivered in this increment

- Tenant-scoped active Brand Knowledge Pack storage seeded from the synthetic ORBITA v1 pack.
- Immutable published version directories and an atomically replaced active-version pointer.
- Draft creation from the active version, section-level draft editing, structural validation and explicit publication.
- Optimistic concurrency: a draft cannot publish if its base version is no longer active.
- Brand identity (`brand_id` and `pack_id`) cannot be changed through a draft.
- Validation for required fields, duplicate fact/policy/asset IDs, status values, policy severities, required record collections and unsafe asset paths.
- Brand Owner-only draft mutation and publication; reviewer/administrator read-only version inspection.
- Audit event on successful publication.
- Every new review uses the active tenant pack and snapshots its fingerprint/content. Historical review snapshots are not rewritten.
- Brand Control Center includes version history, fingerprint display, JSON section editor, validation report and explicit publish confirmation.

## API

- `GET /api/v1/brands/current`
- `GET /api/v1/brands/current/management`
- `GET /api/v1/brands/current/versions`
- `POST /api/v1/brands/current/drafts`
- `GET /api/v1/brands/current/drafts/{draft_id}`
- `PUT /api/v1/brands/current/drafts/{draft_id}/section`
- `POST /api/v1/brands/current/drafts/{draft_id}/validate`
- `POST /api/v1/brands/current/drafts/{draft_id}/publish`

## Storage and trust boundaries

The Build 007 implementation uses a tenant-scoped filesystem store under `data/brand_packs/`, separate from the transactional review database and private uploaded-content storage. Each published version is stored in its own directory. The active pointer is replaced atomically, so readers see either the old complete version or the new complete version.

This is a local/event-build adapter, not a claim of distributed production storage. Cross-process concurrent publication should be moved to a database-backed transaction/lock or an object-store version manifest before multi-instance deployment. Pack mutation is restricted to the Brand Owner role. The Administrator can inspect but cannot silently change brand truth.

## Intentional limitations

- The section editor currently edits JSON structures; a guided form editor can replace it later without changing the API contract.
- Approved asset metadata can be edited, but uploading/replacing binary brand assets and malware scanning are not implemented in this increment.
- Policy/fact content is schema-validated but does not yet have a full typed per-field domain schema for every future brand record type.
- Publishing creates a new pack version for future reviews; automated impact re-review of already-submitted content is not included here.
- The store is filesystem-backed for the single-host event deployment. It is not yet backed by PostgreSQL or S3-compatible object storage.

## Verification

`tests/unit/test_knowledge_pack_store.py` covers seed initialisation, immutable publication, duplicate-ID rejection and stale draft protection.

`tests/integration/test_brand_management.py` covers owner-gated draft/edit/validate/publish, history, and the invariant that an old review retains the old pack fingerprint while later reviews receive the newly published fingerprint.
