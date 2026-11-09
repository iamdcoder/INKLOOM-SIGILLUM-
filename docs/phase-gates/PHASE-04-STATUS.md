# Phase 04 — Brand Control Center and Knowledge Pack lifecycle

**Current status:** CORE WORKFLOW PARTIALLY IMPLEMENTED — database catalogue, explicit owner decisions, controlled PDF/DOCX source intake, fail-closed malware gates, immutable version comparison and deterministic owner-configurable asset usage policies are implemented. **Not signed off.**  
**Implementation baseline:** Build 015, cumulative from Build 014.  
**Database migration head:** `20261109_0005`.  
**Gate:** Owner-controlled and provenance-preserving Knowledge Pack lifecycle. Live PostgreSQL RLS/concurrency, live ClamAV and full frontend quality evidence remain outstanding, as do fully guided forms and broader conflict/source lifecycle controls.

## Product objective

Create the organisation-owned source of truth used by claim, terminology, tone and visual checks. A record may influence future reviews only after it is owner-approved and its containing immutable Knowledge Pack version is published.

## Implemented capability

- [x] Tenant and brand scoped pack namespaces, active heads and version histories.
- [x] Separate pack IDs for distinct brands in the same tenant; new non-demo brands start with empty brand truth.
- [x] One-time Build 007–012 compatibility import of the original brand's published history, active pointer and eligible drafts with fingerprint checks.
- [x] Database-backed immutable snapshots, drafts, active-version pointer and append-only record-decision history; filesystem JSON remains a repairable mirror.
- [x] Draft revision compare-and-swap and guarded publication with PostgreSQL row locks and conditional head updates in code.
- [x] Brand Control Center sections for facts, policies, terminology, voice, approved assets and sources.
- [x] Manual source registration with exact retained excerpt and/or URI provenance. Remote source URIs are never fetched automatically.
- [x] **Build 014:** controlled Brand Owner-only PDF/DOCX upload with file signature validation, size cap, private tenant+brand+draft storage namespace and original SHA-256.
- [x] **Build 014:** fail-closed ClamAV `INSTREAM` scanner for Knowledge Pack source documents and uploaded PNG/JPEG/WebP assets. `INFECTED`, `UNAVAILABLE` and `ERROR` are explicit non-clean states.
- [x] **Build 014:** source parsing runs only after a CLEAN malware scan. It stores a bounded extraction manifest with logical text regions, warnings and parser confidence; it does not expose private storage keys.
- [x] **Build 014:** source download, extraction inspection and approval are blocked until scanner status is CLEAN; uploaded document approval also requires complete non-empty extraction. Owners can retry scanning after service recovery.
- [x] **Build 014:** asset preview/approval are blocked until scan status is CLEAN. Rescanning to a non-clean state suspends the draft asset's previous approval.
- [x] **Build 014:** generic JSON editor cannot inject approval metadata, source binary hashes, storage keys, upload identity, malware results or uploaded-source extraction metadata. Editing an approved record downgrades it to draft for explicit re-approval.
- [x] Owner approve/reject actions for facts, policies, terminology, sources and assets require a decision reason. Approval applies only to the draft until the owner publishes.
- [x] Approved facts require approved source record, exact version and quote traceability; URI-only provenance does not independently substantiate an exact quote.
- [x] **Build 014:** record-level immutable version diff API and Brand Control Center view; sensitive private storage references are redacted and values bounded.
- [x] **Build 015:** owner-configurable usage policies per asset kind: allowed brand channels, allowed declared uses, minimum pixel dimensions, allowed six-digit palette colours, RGB-distance tolerance, minimum measured palette coverage, publication validity window and policy severity.
- [x] **Build 015:** bounded palette extraction is stored when brand raster assets are uploaded; palette validation checks measured coverage and reports `ASSET_PALETTE_UNMEASURABLE` for legacy assets without a measured palette rather than treating absence as a 0% measured score.
- [x] **Build 015:** asset dimensions and palette policy are checked during Knowledge Pack validation; non-zero clear-space policy is an explicit manual-review warning and is never represented as automatically certified.
- [x] **Build 015:** submission form captures a controlled `intended_use` value; the value is stored on the submission and returned in review context.
- [x] **Build 015:** review-time channel/use/validity restrictions are applied only where the submitted image SHA-256 exactly matches an approved asset record. A different flattened creative containing a logo is not automatically identified.
- [x] **Build 015:** Brand Control Center includes a guided per-asset-kind usage policy editor, saving owner policy in the unpublished draft; publication remains required before the policy is authoritative.
- [x] **Build 015:** migration `20261109_0005` adds the submission intended-use field and handles both fresh metadata-created SQLite databases and pre-existing Build 014 schemas.
- [x] SHA-256 integrity validation for uploaded source originals and uploaded assets before serving/validation.
- [x] Pack, source, owner-decision, asset-scan/upload and publication actions are audited.
- [x] Cross-brand API isolation tests prove a draft from one brand cannot be read from another brand in the same tenant.

## Acceptance evidence in Build 015

- `tests/integration/test_brand_management.py`: draft/validate/publish lifecycle; cross-brand isolation; source registry and asset approval; DB-backed reload/stale-draft protection; Build 012 migration; version diff endpoint; PDF/DOCX source upload through scanner outage → clean retry → extraction → download → owner approval; infected source quarantine.
- `tests/unit/test_malware_scanner.py`: INSTREAM framing, CLEAN result, INFECTED result, transport outage and invalid/empty payload handling.
- `tests/unit/test_knowledge_pack_store.py`: uploaded-source extraction provenance cannot be changed through generic JSON; immutable-version diff; private storage key redaction; reference excerpt bounds; minimum dimensions; measured palette rejection; missing palette is explicitly unmeasurable; policy schema validation.
- `tests/unit/test_asset_policy.py`: palette extraction and weighted matching; allowed channel/use and temporal rules; exact-hash review-time restrictions; clear-space manual-review result; non-identical image hashes are not treated as approved asset matches.
- `tests/integration/test_api.py` and `tests/integration/test_brand_management.py`: intended-use API persistence/rejection and owner asset-policy draft → validate → publish workflow.
- Full backend suite: **119 passed, 1 skipped, 0 failed (120 collected)** in the local SQLite test environment. The skipped test is the PostgreSQL-only RLS enforcement test.
- Python `compileall`: passed for backend, apps, migrations, tests and scripts.
- Alembic/database verifier: SQLite current at `20261109_0005`; all 16 required tables present; RLS is not applicable to SQLite.
- Synthetic golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** (12 deterministic synthetic cases; not a general accuracy claim).
- TypeScript compiler API syntax parse: passed for the four changed files (`brand/page.tsx`, `submissions/new/page.tsx`, `reviews/[id]/page.tsx`, `lib/api.ts`). Full `npm ci`, lint, typecheck and production build were not completed: dependency installation timed out and project-local binaries were unavailable.
- ClamAV protocol behaviour is unit-tested using a fake TCP socket; a live daemon/signature-update run was not performed.

## Remaining work before Phase 04 sign-off

- [ ] Run the PostgreSQL CI with a non-superuser `NOBYPASSRLS` application role; prove all four Knowledge Pack RLS policies and concurrent publication under a real PostgreSQL service.
- [ ] Run a live ClamAV Compose integration check, including initial signature database update, scanner outage/recovery and infected test fixture; select a deployment-specific scanner availability/operations policy.
- [ ] Extend review-time asset analysis beyond exact-byte matching to perceptual candidates with conservative thresholds and mandatory human confirmation; do not treat embeddings or perceptual similarity as logo certification.
- [ ] Decide whether palette comparisons need a perceptual colour space (for example, CIE Lab/Delta E) after evaluation on approved brand fixtures; current RGB-distance check is explicitly a rough candidate gate.
- [ ] Add fully guided create/edit forms for the complete fact, policy, terminology and voice record schemas. The asset usage policy editor is now guided, but the JSON editor remains an expert surface for other record classes.
- [ ] Complete normalized schema and conflict validation across scoped facts, policies, terms, voice, assets and sources. The current equal-authority fact/policy and terminology checks are not a complete governance conflict engine.
- [ ] Add source replacement/version lifecycle and compare source versions in a guided change-summary view where source owner expects it.
- [ ] Add retention/deletion controls for quarantined source/asset objects and recovery/cleanup for failed DB registration after a private object has been written.
- [ ] Run full frontend `npm ci`, `npm run lint`, `npm run typecheck`, `npm run build`, then browser walkthrough/manual screenshots at supported laptop and tablet widths.
- [ ] Re-run the full Phase 03 negative-access matrix on PostgreSQL; the frontend and database requirements in that phase are still unsigned.

## Trust boundaries and limitations

- The database is authoritative for pack metadata, immutable version snapshots, drafts, record decisions and active pointer. JSON files are compatibility/export mirrors.
- Original source and asset bytes remain in configured private storage. Browser responses expose authenticated download/preview content, not object storage keys.
- Malware scanning is active only when a reachable ClamAV daemon with usable signatures is configured. Without it, uploads are quarantined and remain unavailable; no bypass is provided.
- Build 014's malware scan covers Knowledge Pack PDF/DOCX source documents and raster brand assets. The normal content-submission upload pipeline remains Phase 05 work and is not claimed to be malware-scanned by Build 015.
- Build 015 palette extraction and comparison is a compact RGB-distance estimate over a bounded thumbnail. It is not ICC-aware colour management, perceptual colour difference, semantic brand-fit analysis or logo identity recognition. A missing palette is unmeasurable and prevents passing a configured palette requirement.
- Build 015 asset usage policy is applied to an uploaded image only on exact SHA-256 equality with an approved asset record. It does not discover logos or other catalogue marks embedded inside a different flattened creative. Clear-space remains manual review.
- Extracted source text is a provenance aid. OCR/parse confidence and completeness remain visible; partial/empty extraction does not satisfy uploaded-source approval.
- Live MinIO/AWS storage, ClamAV runtime, PostgreSQL RLS and row-lock semantics were not exercised in this environment.
- Version diff output is bounded and redacts private storage references. It does not replace signed independent audit checkpoints.
- Source URI records are not fetched and do not independently substantiate a claim. Remote URL retrieval would require a separate SSRF-safe, allowlisted import design.
- Approval remains human-controlled and version-bound. An approved record in a draft is not used by reviews until validation and publication.
- Knowledge-change impact identification and affected-review re-check remain Phase 14 advanced work; historical approvals are not rewritten.

## Decision

**Phase 04 remains open.** Build 015 closes the first implementation of owner-configurable asset usage restrictions and submission intended-use context. It does not close all-record guided forms, broader conflict governance, source replacement/retention lifecycle, live PostgreSQL RLS/concurrency, live ClamAV operation or browser evidence. Those remain acceptance requirements before sign-off.
