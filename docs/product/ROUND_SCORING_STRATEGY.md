# Round Scoring Strategy — Build and Finish

**Source:** `Problemstatemnt(2).pdf`, pages 2–3.  
**Status:** Strategy for execution; not a claim of achieved score or completed feature.

## Round 2 — The Build

| Judging criterion | Points | Product evidence we must produce |
|---|---:|---|
| Core workflow runs end to end | 30 | Live demonstration: upload supported content -> parse/extract -> resolve approved pack -> retrieve evidence -> analyse -> deterministic findings -> correction -> new immutable version -> re-check -> authorised decision -> audit receipt |
| Technical depth and reliability | 25 | Architecture walkthrough, migration-from-zero proof, automated tests, failure-state evidence, hash/provenance verification, permission tests and reproducible deployment |
| Progress against the plan | 20 | Phase-gate register mapped to requirement IDs, tests, commits and demo evidence; explicit deferrals and limitations |
| The three improvements you named | 15 | Separate proof for Proof Ledger/abstention, Scope-Time Truth Resolver and Pixel-to-Claim continuity |
| Usability so far | 10 | Creator/reviewer task walkthrough, responsive states, keyboard path, concise evidence explanation and visible recovery states |

## Round 3 — The Finish

| Judging criterion | Points | Product evidence we must produce |
|---|---:|---|
| Completeness of the product | 25 | Complete Core workflows and documented boundaries |
| The three improvements delivered | 20 | Measured acceptance tests and demo cases for all three named improvements |
| Reliability under normal use | 20 | Repeatable test suite, regression corpus, failure recovery, observability and deployment checks |
| Usability and real-world fit | 20 | User feedback, task completion observations, accessibility review and clear handoffs |
| Documentation and roadmap | 15 | Setup, architecture, provider/reuse disclosure, limitations, privacy/security notes, contribution statement and roadmap |

## Execution implications

1. Build the Core vertical slice before analytics, complex autonomous agents or stretch integrations.
2. Maintain a trace from every requirement to a test and judge-visible screen or evidence artifact.
3. Make the three improvements testable; do not leave them as marketing labels.
4. Every demo must have a deterministic fallback so a model/provider outage does not prevent the core workflow from being demonstrated.
5. Never hide unsupported evidence, parser warnings, low-confidence OCR or operational failure.
