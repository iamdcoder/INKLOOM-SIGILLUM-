# Inkloom Sigillum — Product Charter

## Product definition

Sigillum is a pre-publication brand assurance workspace for organisations whose content is created by employees, agencies and AI-assisted tools. A creator submits campaign copy or static creative with an explicit brand, channel, locale, audience/scope and intended publication time. Sigillum resolves the applicable approved Brand Knowledge Pack, performs bounded specialist checks, applies deterministic policy rules, and returns one consolidated evidence-linked issue ledger.

It is not a generic writing assistant, legal certification engine or autonomous publisher.

## Product promise

- Every material factual finding is traceable to an authorised, approved and applicable source version, with an exact quote and content location.
- Truth can vary by publication date, product, offer, geography, audience, locale and channel.
- Text embedded in images enters the same claim and terminology pipeline as ordinary body copy; image regions remain identifiable.
- The system abstains when evidence is missing, incomplete, inaccessible, conflicting or outside its valid scope.
- Corrections are local, reversible and bound to the exact source content hash. The original file is never silently overwritten.
- Only authorised humans make approval, rejection and override decisions. Sigillum never publishes autonomously.

## Five invariants

| Invariant | Engineering consequence |
|---|---|
| No proof, no SUPPORTED | No decisive factual verdict without applicable approved evidence or a deterministic approved rule. |
| Truth is scoped and time-aware | Resolve facts against intended publication time and product, offer, region, audience, channel and locale scope. |
| Workers have no decision rights | Analysis nodes return candidate findings only; deterministic adjudication sets configured verdict/severity; humans decide approval. |
| Approval is version-bound | Approval binds to content hash/version, Knowledge Pack and policy versions, evidence snapshot, configuration, reviewer and timestamp. |
| Failure is never approval | Parse failure, incomplete extraction, timeout, provider outage, cancellation and exhausted retries remain explicit non-approved states. |

## Event Core scope

- One controlled brand workspace.
- PDF, DOCX, TXT, PNG and JPG submissions.
- Approved facts, policies, terminology, voice examples and assets.
- Claims, terminology, basic tone, OCR-visible text, approved-asset matching and measurable palette/contrast checks.
- Source-linked explanation, constrained corrections, revision history, reviewer decision and audit receipt.

## Explicit non-promises for Core

- Autonomous publishing.
- Full legal advice or legal certification.
- Full WCAG conformance certification.
- Video/animation understanding.
- Arbitrary formats, all languages or enterprise-scale identity/security certification.
- Automatic mutation of authoritative brand policy.

## Roles

| Role | Primary authority | Default restriction |
|---|---|---|
| Creator | Submit, inspect own/shared findings, accept/edit/reject a patch, resubmit | Cannot approve own submission or alter authoritative facts/policies. |
| Agency / contributor | Submit assigned client assets and respond to findings | Cannot browse unrelated brands or change brand truth. |
| Reviewer | Inspect evidence, comment, request changes, approve/reject assigned content | Cannot change policy unless also Brand Owner; cannot approve a different content hash. |
| Brand Owner | Approve Knowledge Pack versions, set scope/validity, resolve ambiguity, approve policy clarification | Cannot silently rewrite historic approvals or bypass access control. |
| Administrator | Manage users, roles, retention and provider disclosures; inspect security metadata | Admin status alone does not grant approval rights or content access. |
| System worker | Execute bounded, scoped processing and persist typed outputs | Cannot approve, publish, mutate knowledge or execute instructions embedded in uploads. |

## Canonical object chain

`submission -> immutable content version -> review run -> finding -> evidence reference -> patch -> human decision -> audit receipt`

Each resubmission creates a new content version and a new review context. Historical records are not edited in place.
