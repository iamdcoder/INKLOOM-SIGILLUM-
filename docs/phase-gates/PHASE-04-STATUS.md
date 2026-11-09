# Phase 04 — Brand Control Center and Knowledge Pack lifecycle

**Implementation status: COMPLETE in Build 016.**  
**Local acceptance: PASSED** for the available SQLite backend/unit/integration environment.  
**External operational acceptance: PENDING** for hosted PostgreSQL RLS/concurrency, a live ClamAV daemon, and the full frontend lint/typecheck/production build.  
**Database migration head:** `20261109_0005`.  
**Cumulative baseline:** Build 016 (Build 001–016).

> This is a deliberate distinction: Phase 04's application workflow and acceptance fixtures are implemented and pass locally. External environment checks are configured in CI but have not yet produced observed run results. Do not treat a workflow definition as a passing CI run.

## Product objective and phase exit gate

Create the organisation-owned source of truth used by claim, terminology, tone and visual checks. A record may influence future reviews only after it is owner-approved and its containing immutable Knowledge Pack version is validated and published.

The Phase 04 exit gate is that a reviewer can trace a finding to the exact approved record, version, owner, validity and source; draft or unapproved knowledge never enters authoritative retrieval. Build 016 supplies the owner lifecycle, provenance and regression evidence for this gate.

## Requirement status

| Requirement | Status | Implementation / evidence |
|---|---|---|
| Tenant + brand-isolated Knowledge Packs | Complete | Separate catalogue/head/draft/version namespaces; new non-demo brands start empty; cross-brand access tested. |
| Pack versions, active pointer and immutable snapshots | Complete | SQLAlchemy catalogue, immutable version snapshots, active head and append-only record decisions; database is canonical and JSON is a repairable mirror. |
| Owner-controlled draft and publication lifecycle | Complete | Draft create/edit, validation, record decisions, publish, mandatory decision reasons, compare-and-swap and version-bound history. Only publication activates a pack. |
| Facts | Complete | Guided creation form; required scope and validity metadata; approved source ID/version and exact quote; quote is checked against retained approved source text. |
| Policy clauses | Complete | Guided creation form; exact approved source/version/quote required for new clauses. Server marks new clauses as provenance-required and rejects client attempts to disable the marker or approve without an exact excerpt. Legacy synthetic seed policies remain compatible. |
| Terminology | Complete | Guided creation form, preferred/prohibited forms, locale, scoped exceptions and preferred-term linkage validation. |
| Voice examples / guidance | Complete | Guided creation form for traits, examples and disallowed patterns; voice guidance remains advisory unless a deterministic brand rule explicitly governs wording. |
| Approved assets | Complete | Private upload, SHA-256, fail-closed malware scan, dimensions, measured palette metadata and owner approval; policy restrictions are applied at review only for exact-hash catalogue matches. |
| Source registry | Complete | Manual URI/excerpt registration and controlled PDF/DOCX private upload, scan, extraction, retry, preview/download gates, provenance and audit. Remote URIs are not fetched. |
| Source replacement and history | Complete | Guarded v1→v2 replacement retains the old source until replacement is CLEAN and extracted; bounded compare endpoint; predecessor/successor and cycle checks. |
| Safe source deletion | Complete | Only unapproved, unreferenced draft sources can be deleted. Referenced/published sources are protected. Deleting a removable latest version restores the prior source's status. |
| Scope and validity conflict validation | Complete | Overlapping facts, policy clauses, terminology locale/scope and voice guidance are checked. Conflict is visible for owner resolution; the system does not silently select a winner. Distinct offer/product scope remains distinct. |
| Brand Control Center usability | Complete | Guided record creation, advanced structured editor, section views, history/diffs and search/filters for product/offer, channel, locale, geography, audience, owner/approver and validity. |
| Pack source/version comparison | Complete | Bounded diff view/API; private storage references are redacted. |
| Temporal truth and evidence provenance | Complete for Knowledge Pack scope | Validity and recorded-version history retained; exact source/version/owner/status/scope are retained; draft and unapproved records excluded from authoritative retrieval. |
| Database migration | Complete locally | Alembic head `20261109_0005`; local verifier sees all 16 required tables. |
| PostgreSQL RLS and concurrent publication | Implemented; external run pending | CI creates a non-superuser `NOBYPASSRLS` app role; RLS test and competing-publication test run in that job. Both are skipped in local SQLite. |
| Live ClamAV service operation | Implemented; external run pending | CI includes live daemon/signature test for clean-file acceptance and EICAR test-signature detection; local tests cover protocol framing, outage, infected and malformed cases. |
| Frontend production quality | Source integration complete; external run pending | TSX syntax parsing passed for changed Knowledge Pack TSX files. CI runs npm ci, lint, typecheck and production build; those hosted results are not yet observed. |

## Build 016 implementation details

### Owner forms and record governance

`apps/web/components/knowledge-record-forms.tsx` supplies guided creation forms for facts, policies, terminology and voice. `apps/web/app/brand/page.tsx` connects the forms to the active draft and owner workflow. The advanced JSON editor remains available for careful record edits; it is not the default create workflow. Server-side validation remains authoritative.

New factual records and new policy clauses require exact excerpts from an approved source record/version. For uploaded PDF/DOCX sources, the source must have a CLEAN scanner result and completed non-empty extraction. Generic JSON editing cannot forge the source-provenance-required marker or bypass the quote check. Editing previously approved material moves it back to draft for a fresh owner decision.

### Conflict validation

The Knowledge Pack validator checks overlapping scope and validity across facts, policies, locale-aware terminology and voice guidance. Wildcard scope is treated as overlapping where appropriate; distinct product/offer scopes are not merged. Conflicts are returned as explicit validation findings. No ranking or model response silently determines brand truth; the Brand Owner resolves the conflict in a new draft and publishes a new immutable version.

### Source replacement and deletion

The source replacement endpoint does not supersede the existing source when the scanner is unavailable, the new binary is infected, parsing fails or extraction is incomplete. On successful scan and extraction, the new source becomes the current candidate and the previous version remains in history. The compare endpoint returns bounded text/metadata differences without object-storage keys. Deletion is blocked for approved, referenced or historically published source objects. A removable latest draft version can be deleted and its predecessor status restored.

### Search and filters

The Brand Control Center includes a filter panel across records and source/asset sections. Filters include free-text search, product/offer, channel, locale, geography, audience, owner/approver and validity window (`current`, `expired`, `future`, `unspecified`, `all`). Filters improve owner navigation; they do not replace API authorization or server-side scope filtering during retrieval.

## Local verification performed for Build 016

- Full local backend/unit/integration suite: **132 passed, 2 skipped, 0 failed (134 collected)**.
- The two skips are explicit PostgreSQL-only checks: row-level security enforcement and concurrent publication. The concurrent-publication test asserts exactly one winner and one rejected contender; it is not represented as locally executed.
- Python compilation: `python -m compileall -q backend apps migrations tests scripts` passed.
- Alembic/database verifier: local SQLite current at `20261109_0005`; all 16 required tables present. SQLite has no PostgreSQL RLS/pgvector semantics, so those are not inferred.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** across 12 deterministic synthetic cases. The manual case is visual asset identity/contrast; this is not a general accuracy claim.
- TypeScript compiler API syntax parsing: passed for `apps/web/app/brand/page.tsx` and `apps/web/components/knowledge-record-forms.tsx`.
- `.github/workflows/ci.yml` parsed successfully and defines `backend`, `backend-postgres`, `clamav-live` and `frontend` jobs.
- `npm run lint` could not start locally because the project-local ESLint executable is absent (`eslint: not found`). Full frontend `npm ci`, lint, typecheck and production build are therefore **not verified in this environment**. The CI job is configured but is not a substitute for an observed passing run.
- Docker and `psql` are not installed in this authoring environment; live PostgreSQL and live ClamAV were not run here.

## Remaining operational checks (not unimplemented Phase 04 features)

1. Run the `backend-postgres` CI job and retain the run URL/result. It must prove the RLS negative-access matrix with the configured non-superuser role, and the concurrent publish test must confirm one immutable publication only.
2. Run the `clamav-live` job and retain its run URL/result. Confirm daemon startup/signature readiness, CLEAN test file and EICAR signature detection.
3. Run the `frontend` job and retain the run URL/result for `npm ci`, lint, typecheck and production build. Follow with a browser walkthrough at supported laptop/tablet widths and retain screenshots.
4. Record job IDs and any remediation below before describing the cumulative release as operationally verified.

| External check | Run / evidence | Result |
|---|---|---|
| PostgreSQL RLS + concurrent publication | Not run in this authoring session | Pending |
| Live ClamAV | Not run in this authoring session | Pending |
| Frontend lint/typecheck/build | Local ESLint unavailable; CI not yet observed | Pending |
| Browser walkthrough / screenshots | Not run in this authoring session | Pending |

## Trust boundaries and deliberate limitations

- PostgreSQL RLS and true row-lock/concurrent-publication semantics remain dependent on a passing PostgreSQL CI run. SQLite results do not establish them.
- ClamAV scanning is fail-closed. If the daemon or signatures are unavailable, the upload remains unavailable; there is no “skip scan” approval path.
- Remote source URIs are stored as provenance metadata but are not fetched. Any future URL ingestion requires an allowlisted SSRF-safe fetch adapter.
- Exact policy excerpt matching proves that the quote appears in the retained approved source text; it is not an independent legal interpretation of the policy.
- Raster palette policy is a bounded RGB-distance estimate, not ICC-aware or perceptual colour measurement. Clear-space requires human inspection.
- Asset use restrictions require exact SHA-256 equality with the approved asset. A logo embedded in a different flattened creative is not automatically recognised; perceptual matching is a candidate signal for later specialist-analysis work, not certification.
- Automatic Impact Radar and re-review triggered by future Knowledge Pack changes are Phase 14 advanced work. Historic approval receipts are not rewritten.
- Automated TTL retention purge and storage-orphan reconciliation remain operational hardening; safe source deletion and reference protection are implemented for the owner-managed draft lifecycle.

## Gate decision

**Phase 04 implementation is closed in Build 016.** The owner-controlled Knowledge Pack lifecycle, source traceability, record validation, scoped conflict handling, source replacement/deletion and version history are implemented and covered by local regression tests. The external checks above remain open release-assurance items; do not state that PostgreSQL RLS, live malware scanning or full frontend build have passed until their CI results are observed and recorded here.
