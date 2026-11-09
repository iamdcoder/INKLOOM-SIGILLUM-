# Build 015 — Owner-configurable asset usage policies

## Scope

Build 015 extends the Brand Control Center with owner-configurable usage rules for approved raster assets and adds declared intended use to submission context. It is a deterministic rules layer over approved metadata; it is not logo recognition or autonomous visual certification.

## Policy contract

Policies are stored in the `assets.usage_policies` object, keyed by asset kind (`logo`, `product_image`, `campaign_image`, `icon`, `other`). Supported fields:

| Field | Meaning |
|---|---|
| `allowed_channels` | Optional list of channel identifiers already declared by the brand. |
| `allowed_uses` | Optional values from the controlled intended-use enum. |
| `min_width`, `min_height` | Minimum raster pixel dimensions. |
| `palette_hex` | Optional list of six-digit RGB hex colours. |
| `palette_tolerance` | Maximum Euclidean RGB distance, from 0 to 441.7. |
| `minimum_palette_match_ratio` | Minimum weighted palette share within tolerance, from 0 to 1. |
| `clear_space_ratio` | Required proportional clear space, from 0 to 0.5. Non-zero values require human inspection. |
| `valid_from`, `valid_until` | Optional timezone-aware ISO-8601 policy validity bounds. |
| `severity` | `blocking`, `review_required`, `suggestion` or `informational`. |

The guided UI edits the active draft only. Policy has no authority until the entire Knowledge Pack draft is validated and published by an authorised Brand Owner.

## Palette measurement

Newly uploaded brand raster assets store a bounded thumbnail-derived weighted palette. Fully transparent pixels are excluded. Validation compares the retained palette to the owner-authored palette using a weighted RGB Euclidean-distance tolerance. An asset with no stored measured palette returns `ASSET_PALETTE_UNMEASURABLE` when a palette rule is configured. Invalid policy colour values are rejected by schema validation and are not sent to the comparator.

This is not an ICC-aware or perceptual colour model. It is sensitive to image rendering, compression and sampling. It must not be represented as colour certification or semantic brand-fit. The current implementation deliberately keeps clear-space geometry as human review because it depends on the surrounding creative layout.

## Runtime enforcement

Submissions declare one of: `general`, `brand_lockup`, `campaign`, `product_detail`, `social_ad`, `email_banner`, `website_hero`, `packaging`. The value is persisted on `submissions.intended_use` and returned in review serialization.

Review-time restrictions are applied only to image submissions whose `ContentVersion.sha256` exactly equals the SHA-256 of an approved asset record. For that byte-identical match, the service checks declared channel, intended use, policy validity and asset validity at the intended publication time. A mismatch produces a deterministic finding with the policy record in evidence. A non-zero clear-space ratio adds a manual-review finding.

No perceptual hash, embedding or visual logo recognition is used as a decisive signal. A different flattened creative that contains a logo is not identified by this feature. That is explicitly deferred until a measured candidate-matching path with human confirmation is available.

## Database migration

Alembic revision: `20261109_0005_submission_intended_use` (down revision `20261109_0004`). Adds a non-null `intended_use` column with server default `general`. The migration checks the existing column list to support both a pre-existing Build 014 database and a fresh schema where metadata creation may already have created the column.

## Verification

- Backend: 119 passed, 1 skipped, 0 failed (120 collected) in local SQLite mode.
- Focused asset-policy tests cover palette extraction, weighted matching, input validation, allowed channel/use, validity, exact-hash usage enforcement, minimum dimensions, palette non-match and unmeasurable palette.
- Integration tests cover API intended-use persistence/rejection and owner draft → validate → publish policy workflow.
- Migration lifecycle test covers the Build 014 to Build 015 SQLite upgrade.
- Database verifier: current at `20261109_0005`; all 16 required tables present.
- Golden evaluation: 11 PASS, 1 MANUAL_REVIEW_REQUIRED, 0 FAIL.
- Modified TS/TSX files pass TypeScript compiler API parsing. Full npm install, lint, typecheck and production build remain unverified because `npm ci` timed out and project-local binaries were not available.

## Still open

Live PostgreSQL RLS and publication concurrency; live ClamAV integration; complete guided forms for facts, policies, terms and voice; full conflict governance; source replacement and retention cleanup; browser QA; and Phase 04 gate sign-off.
