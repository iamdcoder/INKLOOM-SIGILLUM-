# Phase 04 — Brand Control Center and Knowledge Pack lifecycle

Status: **CORE LIFECYCLE IMPLEMENTED; ASSET AND ADVANCED GOVERNANCE WORK REMAINS**

## Completed in Build 007

- [x] Active pack is tenant-scoped and resolves to an explicit immutable version.
- [x] Brand Owner can create a draft from the active published snapshot.
- [x] Brand Owner can edit brand, facts, policies, terminology, voice and asset-manifest sections in draft state.
- [x] Validation rejects missing identity/required collections, duplicate IDs, invalid statuses/severities and unsafe asset paths, including Windows drive and backslash traversal forms.
- [x] Pack ID and brand ID are immutable through the editor.
- [x] A valid draft can be published as a new immutable version.
- [x] A stale draft cannot overwrite a newer publication.
- [x] Reviewer/administrator version inspection is read-only; only Brand Owner can mutate/publish.
- [x] Publication is audited.
- [x] New reviews bind to the current active pack; previous review snapshots remain unchanged.

## Remaining

- [ ] Guided forms instead of JSON-only section editing.
- [ ] Binary asset upload, validation, malware scanning and preview management.
- [ ] Per-record owner, approval and validity workflow beyond the current pack-level publication.
- [ ] Source-document import with source lineage for Knowledge Pack facts/policies.
- [ ] Automated impact identification/re-review after governing fact or policy changes.
- [ ] Multi-process-safe publication locking and production-grade object storage.

## Exit evidence

- Unit and integration tests in `tests/unit/test_knowledge_pack_store.py` and `tests/integration/test_brand_management.py`.
- API endpoint contract visible in FastAPI OpenAPI.
- Manual UI walkthrough and screenshots still to be collected from the Windows development machine.
