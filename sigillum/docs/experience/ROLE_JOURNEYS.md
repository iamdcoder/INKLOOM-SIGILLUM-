# Role Journey and Handoff Catalogue

## Journey A — Creator submits and corrects content

**Entry:** creator has access to a workspace and brand.

1. Start submission.
2. Select brand, channel, locale, audience/scope and intended publication time.
3. Upload supported file; show accepted types, size limit and processing/privacy notice.
4. Validate intake; preserve original; show submission ID, content hash and immutable version.
5. Display extraction status and warnings.
6. Display the issue ledger with risk-first ordering.
7. Open each finding to inspect exact source text/region and governing evidence.
8. Compare suggested correction; accept, edit or reject with optional reason.
9. Run regression checks; block patches that introduce unsupported claims or remove required qualifiers/disclaimers.
10. Create new immutable version; rerun affected checks.
11. Track reviewer decision and audit receipt.

**Failure/alternate paths:** unsupported file; malformed/oversized file; parser partial success; OCR low confidence; provider unavailable; evidence absent/conflicting; stale patch base hash; permission denied; job timeout/cancelled.

## Journey B — Reviewer resolves a review

**Entry:** reviewer has assigned review permission.

1. Open Review Queue and inspect risk, age and assignment.
2. Open review snapshot and verify content hash and pack/policy context.
3. Inspect highest-risk finding first.
4. Follow content locator to exact text span/page/region.
5. Inspect evidence source/version, scope, owner and validity.
6. Comment or request changes; or decide approve/reject.
7. Override only when privileged, with linked finding and mandatory rationale.
8. Persist version-bound decision and audit receipt.

**Guardrails:** approval disabled for incomplete/failed review, changed content hash, missing required permissions or unresolved blocking policy conditions.

## Journey C — Brand Owner governs truth

1. Open Brand Control Center.
2. Create a draft Knowledge Pack version.
3. Import/add facts, clauses, terminology, voice examples and assets.
4. Attach source references, owner, scope, status, effective dates and qualifiers.
5. Validate missing metadata, overlap and conflicting equal-authority records.
6. Preview change diff and impacted records/reviews.
7. Approve and activate new version.
8. Preserve prior versions and create re-review candidates where policy says impact exists.

**Guardrails:** no in-place edits to approved historical records; new version required; unresolved conflicts remain visible.

## Journey D — Agency contributor works within assignment

1. Open assigned campaign/brand only.
2. View scoped pack material and submission metadata.
3. Upload and resolve permitted findings.
4. Respond to reviewer comments and resubmit.
5. Access only files and exports explicitly granted.

**Guardrails:** cross-brand retrieval is denied; internal notes and unrelated packs remain inaccessible.

## Journey E — Administrator operates workspace

1. Invite/activate/deactivate members and assign roles.
2. Configure safe session and retention settings.
3. Review provider/data-egress register and service health.
4. Inspect audit/security metadata and export permitted reports.

**Guardrails:** admin status does not imply content access or review approval rights.

## Handoff invariants

- Every assignment has an actor, resource, scope and timestamp.
- Every material decision references one exact content version and review context.
- Every requested change is visible to the creator with actionable comments.
- Every role transition is server-authorised; frontend role labels are presentation only.
