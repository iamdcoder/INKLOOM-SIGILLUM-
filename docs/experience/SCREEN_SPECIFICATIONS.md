# Screen Specifications — Phase 01

The following are design contracts for later implementation, not implemented screens.

## 1. Overview

**Purpose:** answer what needs attention now.

**Hierarchy:** page title + brand/workspace context; compact operational summary; risk-ranked review queue; recent activity; system health and outstanding Knowledge Pack changes.

**Key interactions:** filter by brand/status/owner/date; open submission or review; create submission; jump to overdue/failed jobs.

**Must show:** counts are scoped and timestamped; pending/failed work is not counted as approved; provider health is not confused with content compliance.

## 2. Submissions

**Purpose:** create and track immutable content versions.

**Core elements:** submission list/table; file type/size; brand/channel/locale; intended publication time; creator; version; content hash (progressively disclosed); parse state; review state; last updated.

**Upload flow:** drag/drop and file picker; explicit supported formats PDF/DOCX/TXT/PNG/JPG; file validation; scope metadata; privacy/provider notice; upload progress; quarantine/parse result.

**Must show:** original is retained; a new upload/edit creates a new version; invalid/unsupported/oversized files have actionable errors.

## 3. Review Workbench

**Purpose:** let a reviewer understand the most important issue, inspect its proof and take the correct next action.

**Desktop layout:**

- Header: submission identity, exact version, review status, publication context, pack/policy version and assignment.
- Left document stage: PDF page navigation/zoom/thumbnails; DOCX/TXT paragraph/line navigation; image preview with OCR/asset overlays.
- Right issue ledger: risk-ranked findings with filters for severity, verdict, category, source, location, status and confidence.
- Finding detail (side panel or expanded inspector): concise explanation, verdict, severity, evidence sufficiency, confidence, extraction confidence, policy rule, exact quote, source record/version, owner, scope and validity.
- Action area: comment, request changes, open correction, approve/reject/authorised override according to role/state.

**Location rules:** PDF uses page and canonical region coordinates mapped to rendered coordinates; DOCX/TXT use paragraph/line and offsets; PNG/JPG use pixel-normalised boxes and OCR confidence. Never fabricate coordinates where a parser cannot supply them.

**Risk-first rules:** highest-risk unresolved issue is obvious without reading every finding. Every substantiated finding opens both exact content location and exact source evidence. Inadequate evidence is labelled honestly.

## 4. Correction Studio

**Purpose:** propose minimal, reversible, purpose-preserving changes.

**Core elements:** original content; proposed version; diff; linked finding; patch base hash; source and policy references; preserved intent rubric (audience, offer, CTA, qualifiers, core meaning); regression results.

**Actions:** accept, edit, reject, undo local edit, compare versions and create new immutable version.

**Safety:** patch invalidates if current content hash differs from base hash. A PDF/image text replacement is an instruction/proposal unless the original flattened asset was actually edited. Show before/after; never claim a file was modified when it was not.

## 5. Reviewer Console

**Purpose:** manage assigned work.

**Core elements:** assigned/unassigned queues (permission-gated), age, SLA/urgency, risk, owner, brand, submission version, unresolved findings and decision status.

**Actions:** claim, assign, comment, request changes, approve, reject, authorised override.

## 6. Brand Control Center

**Purpose:** own approved brand truth.

**Sections:** Pack overview/version history; Facts; Policy clauses; Terminology; Voice examples; Approved assets; Owners and source records.

**Core metadata:** owner, source reference, approved/draft status, version, scope, effective start/end, qualifiers, locale/channel/product/geography where applicable.

**Actions:** draft, import, validate, resolve conflict, preview diff, submit for approval, approve new version.

## 7. Governance / Impact Radar

**Purpose:** reveal recurring problems and policy ambiguity without mutating policy autonomously.

**Core views:** recurring issue categories, overrides, unverifiable claims, stale facts, impacted reviews, repeated terminology/tone issues, proposed clarification queue.

**Actions:** inspect cluster, compare versions, draft clarification, request owner review, enqueue controlled re-review.

**Guardrail:** insight is not a policy change. Brand Owner approval creates the new policy/pack version.

## 8. Administration / Audit

**Purpose:** manage workspace configuration and explain what happened.

**Core views:** members/roles; sessions; retention; provider register; security events; audit timeline; authorised export.

**Guardrail:** administrator role does not automatically grant content visibility or approval privileges.
