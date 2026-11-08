# Build 012 — Brand Control Center, scoped Knowledge Packs and record governance

**Date:** 2026-11-09  
**Base:** Build 011 (cumulative; includes Builds 001–011)  
**Phase:** 04 — Brand Control Center and Knowledge Pack lifecycle  
**Gate:** Phase 04 remains partially complete; see `docs/phase-gates/PHASE-04-STATUS.md`.

## Problem addressed

Build 011 had moved identity and authorization to tenant/brand memberships but the Knowledge Pack store still used a tenant-only namespace. That created a data-integrity risk for tenants with multiple brands: packs could collide or share the synthetic ORBITA seed data. A workspace permission model is not sufficient unless its brand truth is partitioned by the same brand boundary.

## Architecture changes

### Brand-scoped namespace

The filesystem store now uses:

```text
<root>/<tenant-id>/brands/<brand-id>/<pack-id>/
  active.json
  versions/<version-id>/
  drafts/<draft-id>.json
```

The default ORBITA demo brand preserves the existing seed/legacy migration path. Other brands receive a neutral starter snapshot with empty factual, policy, terminology, asset and source collections. The one-time compatibility migration copies the old tenant-only pack only to the original ORBITA brand ID. It does not infer that a tenant's other brands should inherit ORBITA facts/assets.

### Source registry

`BrandPack` and its snapshot now support an optional `sources` section. Build 012 records source ID, name, type, source version, owner, status, approval provenance, validity, reference excerpt and/or HTTP(S) URI. When exact reference text is supplied, the text hash is recorded. Source URLs are metadata only and are never fetched by this service; arbitrary URL fetch remains out of scope.

### Record decisions

The record-decision service supports fact, policy, terminology, source and asset records. Owner decisions set status and append decision metadata into the draft snapshot. A positive decision is not live brand truth until the containing pack has passed validation and a Brand Owner publishes a new immutable version. Rejected/draft terminology is excluded from the deterministic terminology worker. Historical seed terminology without an explicit status is treated as legacy-approved for backward compatibility.

### Private uploaded assets

Brand Owners can upload PNG/JPEG/WebP assets into private object storage. The API validates decoded image format, image dimensions/pixel count and configured byte limits, then stores the exact byte hash and metadata. SVG is rejected by the upload path. The draft preview and published asset route return private, no-store responses with `nosniff`; uploaded raster bytes are SHA-256 verified on read. Draft validation re-reads and verifies every approved uploaded asset before publication.

This is not malware scanning, a DAM integration or automated logo/asset identity certification. Existing SVG fixtures are legacy reference assets, not a supported upload type.

## API additions

| Method | Route | Purpose |
|---|---|---|
| POST | `/brands/current/drafts/{draft_id}/sources` | Register a draft source record; does not fetch remote URI |
| POST | `/brands/current/drafts/{draft_id}/records/{record_type}/{record_id}/decision` | Brand Owner approve/reject/draft/not_approved a fact, policy, term, source or asset |
| POST | `/brands/current/drafts/{draft_id}/assets` | Upload bounded raster asset into private storage as draft |
| GET | `/brands/current/drafts/{draft_id}/assets/{asset_id}` | Brand Owner preview with SHA-256 verification |
| GET | `/brands/current/assets/{asset_id}` | Serve an approved published asset in the selected brand with SHA-256 verification |

Existing pack management/draft/section/validate/publish routes now pass the selected `brand_id` into the pack store. API identity/permission resolution remains governed by the persisted Build 011 membership context.

## Validation rules added or strengthened

- Approved facts must have approval provenance and link to an approved source record; source version and quoted excerpt are checked against the registry.
- A fact's `source_ref.source_version` must match the approved source registry version.
- Source records require unique IDs, supported source type, positive integer version, valid HTTP(S) URI syntax when present, valid SHA-256 syntax and timezone-aware validity bounds.
- Approved sources require approval identity/time plus an evidence reference (hash, excerpt or URI).
- Terminology records require unique IDs and text; explicit statuses are validated; approved terms require approval identity/time.
- Approved uploaded assets require approval provenance, tenant+brand-prefixed object key, object existence and a SHA-256 match against the bytes in private storage.
- Draft-only changes do not change the active pack used by new reviews.

## Tests and results

- Backend: **96 passed, 1 skipped** (SQLite/local suite). The one skip is the PostgreSQL-only RLS integration check, not a Phase 04 test.
- `python -m compileall -q backend apps migrations tests scripts`: passed.
- TypeScript/TSX syntax transpilation: 15 source files, zero syntax diagnostics. Full Next.js lint/typecheck/build remains unverified because the local dependency installation is unavailable in this session.
- Golden corpus: 11 automated PASS, 1 intentionally manual visual review, 0 FAIL.
- No database migration was needed: new source and record-decision metadata are stored within immutable JSON pack snapshots, and the asset binaries use the existing storage adapter.

## Known limitations

- Pack metadata/drafts remain filesystem-backed and rely on an in-process lock; not a multi-host/distributed publication guarantee.
- No controlled PDF/DOCX source ingestion/import or remote URI fetch.
- No malware scanning/quarantine service.
- No production MinIO/AWS run observed.
- No complete owner-controlled guided forms for every fact/policy/term/voice attribute; expert JSON section editor remains.
- No automated knowledge-change impact graph/re-review; that is Phase 14.
- Phase 03 PostgreSQL RLS CI and frontend production gates are still outstanding.
