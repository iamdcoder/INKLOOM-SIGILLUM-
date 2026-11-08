# Inkloom Sigillum — Build 012 handoff

**Build:** 012  
**Baseline:** Build 011 (cumulative source snapshot; includes Builds 001–011)  
**Milestone:** Phase 04 — Brand Control Center and Knowledge Pack lifecycle  
**Phase status:** Partially implemented; not signed off  
**Date:** 2026-11-09

## What changed in Build 012

Build 011 had persisted tenant/brand membership and permission context, but the Knowledge Pack store still had a tenant-only namespace. Build 012 aligns Knowledge Pack isolation with the selected brand boundary.

1. **Tenant + brand namespace.** Pack versions and drafts are stored under a brand-specific path. A new non-demo brand starts with neutral empty knowledge rather than receiving ORBITA's demo facts, policies, terminology, assets or sources.
2. **Legacy compatibility.** The old tenant-only pack is copied once into the original ORBITA brand namespace only. The migration does not copy it into sibling brands.
3. **Source registry.** Brand Owners can register source type, version, owner, status, validity, excerpt and/or URI metadata. URLs are not fetched. A source does not become authoritative merely because it has been registered or approved inside a draft.
4. **Record decisions.** Brand Owners can approve, reject, return to draft or mark facts, policies, terminology, sources and uploaded assets as not approved. A non-empty reason is mandatory and the decision remains part of the draft until the entire pack is validated and published.
5. **Private brand asset upload.** The API accepts bounded PNG/JPEG/WebP raster images, validates decoded format and dimensions, stores them in the existing private object-storage adapter and records the SHA-256 hash. SVG is rejected by this upload path.
6. **Asset integrity.** Approved uploaded asset bytes are checked during draft validation and again when previewed or served. Storage keys are checked against the active tenant+brand prefix.
7. **Fact/source provenance.** Approved facts require approval provenance and an approved source record with matching source version. Where an excerpt is stored, the cited quote must be present in that excerpt. Source excerpt hashes are checked.
8. **Terminology governance.** Explicitly draft/rejected terminology is no longer used by the verification engine. Historical seed terminology with no status remains legacy-approved for compatibility.
9. **Documentation and regression coverage.** Phase status, API semantics, requirement traceability, build log and tests are updated.

## Verification performed

- Backend suite: **96 passed, 1 skipped**. The skip is the PostgreSQL-only RLS runtime test, which requires PostgreSQL and is part of the pending Phase 03 external gate.
- Python compilation: `python -m compileall -q backend apps migrations tests scripts` — passed.
- Database verifier: SQLite schema is current at Alembic revision `20261109_0003`; all 12 required tables are present. Build 012 adds no database migration.
- Golden evaluation: **11 PASS / 1 MANUAL_REVIEW_REQUIRED / 0 FAIL** across 12 synthetic cases. This is deterministic fixture evidence, not a claim of general model accuracy.
- Frontend syntax: **15 TypeScript/TSX source files, zero syntax diagnostics** using TypeScript `transpileModule`. This does not prove type correctness or a production build.
- Full `npm ci` timed out in the authoring environment. Full Next.js lint, typecheck and production build are therefore **not verified**.
- Live PostgreSQL RLS and live MinIO/AWS storage were not available and remain unverified.

## Known limitations / Phase 04 still open

- Pack metadata, drafts, decisions and active pointer remain filesystem-backed. The lock is process-local; this is not safe for multi-host concurrent publishing.
- No normalized PostgreSQL pack tables or transactional pack-manifest adapter yet.
- No controlled PDF/DOCX source import, remote URI fetch or malware scanning/quarantine.
- No full guided record forms for all fact, policy, terminology and voice-example attributes; the structured JSON section editor remains available.
- Advanced owner controls for allowed asset use, min dimensions, palette, clear-space, scope and validity still need implementation and enforcement.
- More comprehensive conflict detection and an owner-visible side-by-side pack version diff remain outstanding.
- Formal browser walkthrough screenshots and full frontend quality gates remain outstanding.
- Impact dependency graph and automatic re-review after knowledge changes belong to Phase 14, not this build.
- Phase 03 remains unsigned until the non-superuser PostgreSQL RLS CI run and full frontend quality gates pass.

## Apply this cumulative build

1. Back up the existing repository and local database.
2. Extract `Sigillum_Build_012.zip` over the existing repository root.
3. Preserve your local `.env`, `.git`, `data/`, `.venv/` and `apps/web/node_modules/`. These local items are not part of the archive.
4. Activate your existing Python virtual environment and run the checks below.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python scripts/verify_database.py
pytest -q
python scripts/evaluate_golden_cases.py
python -m compileall -q backend apps migrations tests scripts
```

No new Alembic migration is introduced in Build 012; `20261109_0003` remains the expected database head.

For the frontend, from `apps/web`:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```

Record the actual outputs before marking those gates complete. If `npm ci` fails, do not infer a successful frontend build from the syntax-only check.

## Integrity and scope

The archive is a cumulative source snapshot. It excludes `.git`, `.env` files, local databases, user uploads, virtual environments, `node_modules`, build caches and Python bytecode. Do not apply this ZIP as a second separate patch on top of another Build 012 copy.

**Definition of done for this increment:** brand-specific knowledge separation, source/record/asset governance and their current regression suite are implemented. **Definition of done for Phase 04 is not met yet**; see `docs/phase-gates/PHASE-04-STATUS.md`.
