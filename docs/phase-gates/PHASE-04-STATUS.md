# Phase 04 — Brand Control Center and Knowledge Pack lifecycle

**Current status:** CORE WORKFLOW PARTIALLY IMPLEMENTED — MULTI-BRAND ISOLATION AND RECORD GOVERNANCE IMPROVED IN BUILD 012.  
**Implementation baseline:** Build 012, cumulative from Build 011.  
**Gate:** Not signed off. Filesystem-backed pack metadata, distributed locking, source-document import, malware scanning and formal browser walkthrough evidence remain outstanding.

## Product objective

Create the organisation-owned source of truth used by claim, terminology, tone and visual checks. A record may influence future reviews only after it is owner-approved and its containing immutable Knowledge Pack version is published.

## Implemented capability

- [x] Tenant and brand scoped pack namespaces: `<pack-root>/<tenant>/brands/<brand>/<pack-id>/`.
- [x] Separate pack IDs for distinct brands in the same tenant.
- [x] A new non-demo brand starts with empty facts, policies, terminology, assets and sources; ORBITA demo content is not copied into sibling brands.
- [x] One-time Build 007–011 compatibility migration copies the historical tenant-only pack only into the original ORBITA brand namespace.
- [x] Immutable published versions, active pointer, draft creation, stale-draft detection, explicit validation and owner-only publication.
- [x] Brand Control Center sections for Facts, Policies, Terminology, Voice Examples, Approved Assets and Sources.
- [x] Source registry records with type, source version, exact pasted reference excerpt and/or URI metadata, SHA-256 when excerpt text is supplied, owner, state and validity.
- [x] Source URLs are registered as provenance only; Sigillum does not fetch them automatically.
- [x] PNG/JPEG/WebP asset upload to private object storage with decoded-image validation, dimensions, size cap, SHA-256, draft state and preview.
- [x] SVG rejected from the new upload route; raster asset MIME is selected from decoded file format, not the browser's claimed content type.
- [x] Per-record owner approve/reject actions for facts, policies, terminology, sources and uploaded assets, including a reason in the audit record.
- [x] A record-level approval remains inside the draft. It is not authoritative for new reviews until the Brand Owner validates and publishes the containing pack.
- [x] Approved facts must link to an approved source registry record, exact source version and a quote present in the approved source text where text is stored.
- [x] Approved terminology must carry approver identity/time; the verification engine now ignores explicitly draft/rejected terminology while treating historical seed records with no status as legacy-approved.
- [x] Approved uploaded asset bytes are SHA-256 checked at validation and again on preview / published retrieval; storage keys must remain inside the current tenant+brand namespace.
- [x] Pack, source, record-decision, asset-upload and publication actions are audited.
- [x] Cross-brand API isolation tests prove a draft created for one brand cannot be read from another brand in the same tenant.

## Acceptance evidence in Build 012

- `tests/unit/test_knowledge_pack_store.py`: brand-scoped namespace, one-time legacy migration, exact approved source-version binding.
- `tests/unit/test_verification_engine.py`: rejected terminology does not remain an active rule.
- `tests/integration/test_brand_management.py`: cross-brand isolation; source registry and uploaded asset lifecycle; preview and published-asset integrity checks; unsupported SVG/non-image rejection; non-owner source creation/decision denial.
- Full backend suite: **96 passed, 1 skipped**. The skipped check is the PostgreSQL-only RLS runtime test; it belongs to the Phase 03 hosted PostgreSQL gate.
- Python `compileall`: passed.
- Frontend TypeScript/TSX syntax transpilation: 15 files checked, 0 syntax diagnostics. This is not a substitute for project-wide `npm run lint`, `npm run typecheck` or `npm run build`.
- Synthetic golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** (12 cases; not a general accuracy claim).

## Remaining work before Phase 04 sign-off

- [ ] Move pack metadata, draft state, record decisions and active-version pointer into transactional database tables (or a rigorously designed shared version-manifest service); the current filesystem store is single-host.
- [ ] Add cross-process/distributed publication locking. The current in-process lock is not a multi-instance concurrency guarantee.
- [ ] Implement controlled PDF/DOCX source-document import with page/paragraph provenance, extraction warnings, content hash and source approval workflow.
- [ ] Add malware scanning/quarantine for uploads. Current brand asset intake permits bounded PNG/JPEG/WebP decoding and validation only; it is not a malware scanner.
- [ ] Add owner configuration for allowed asset use, minimum dimensions, palette, clear-space and scope/validity constraints, then enforce them in validation.
- [ ] Add guided create/edit forms for all fact, policy, terminology and voice fields. JSON editor remains as an expert editing surface.
- [ ] Add stronger normalized record schemas and conflict checks for all active fact/policy/term/source combinations.
- [ ] Add owner-visible version comparison and detailed change summary beyond the current immutable history list.
- [ ] Collect browser screenshots/manual walkthrough evidence on the participant's Windows environment after full frontend lint/typecheck/build.
- [ ] Keep knowledge-change impact identification and affected-review re-check in Phase 14; do not mutate historical approvals.

## Trust boundaries and limitations

- Knowledge Pack metadata and immutable versions remain filesystem-backed for the current single-host event build. They are brand isolated, but not production multi-instance safe.
- Binary uploads use the private object storage adapter. Live MinIO/AWS operation has not been exercised here.
- Source URI records are not fetched and do not independently substantiate a claim. The user must preserve approved excerpt/source evidence in the record.
- SVG remains unsupported for new asset uploads. Existing seeded SVG is a static reference asset and does not imply a general SVG upload pipeline.
- Image validation is not malware scanning or a certification of asset identity/brand fit.
- Approval is versioned and human-controlled. A source/record marked approved in a draft cannot affect reviews until that draft is validated and published by a Brand Owner.
- PostgreSQL RLS and frontend production gates remain pending from Phase 03; this file does not sign them off.

## Decision

**Phase 04 remains open.** Build 012 closes the multi-brand pack isolation gap and adds source/asset/record workflows, but the remaining items above are required before calling the full phase complete.
