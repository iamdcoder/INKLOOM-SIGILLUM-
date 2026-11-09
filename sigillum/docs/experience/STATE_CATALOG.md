# UI State Catalogue

A state is part of the product contract. Every state below must have a designed presentation, user action and test.

| State | Trigger | Required presentation | Permitted action / guardrail |
|---|---|---|---|
| Loading | Initial data fetch | Skeleton matching final layout; preserve context | No premature success or approval |
| Empty | No submissions/findings/queue items | Explain why empty and the next valid action | Create/upload only if permitted |
| Validation error | Invalid metadata or form value | Field-level message and summary | Preserve inputs; focus first error |
| Uploading | File transfer in progress | Progress, filename, cancellation where safe | Never call it parsed or reviewed |
| Quarantined | File awaiting validation/scan | Persistent intake status | No parsing/review until cleared |
| Unsupported / oversized | Type/signature/size invalid | Exact supported constraints and safe recovery | Reject intake; do not silently ignore |
| Parsing | Extraction running | Stage, safe progress and elapsed state | No review decision yet |
| Partial parse | Some content/regions unavailable | Persistent warning and affected locations | Route uncertain areas to manual review |
| Low OCR confidence | Region below configured threshold | Highlight region and extraction confidence | Do not silently treat OCR text as certain |
| Queued / running | Durable job accepted | Job ID, stage, updated time, reconnect/poll state | Safe cancel/retry controls |
| Provider unavailable | External dependency failure | Provider-safe code, affected capability, fallback/retry | Non-approved operational state |
| Timed out / retry exhausted | Job budget consumed | Explicit failure and correlation ID | Never imply completion/approval |
| Cancelled | User/system cancellation | Cancellation state and retained partial trace | No approval |
| Stale review context | Pack/policy changed since review | Show previous and current versions | Re-review according to policy; preserve old receipt |
| Stale patch | Content hash differs from patch base | Explain mismatch; disable apply | Reconcile/regenerate patch |
| Permission denied | Actor lacks action/resource scope | Explain unavailable permission without leaking resource data | No data fetch from disallowed scope |
| Conflict | Concurrent or incompatible change | Show safe conflict context | Reconcile; no last-write-wins on governed data |
| Needs review | Analysis complete with unresolved findings | Risk-first ledger | Human action required |
| Approved | Exact version/context approved by authorised reviewer | Receipt with reviewer/time/hash/context | No approval inferred from client state |
| Rejected / overridden | Authorised decision recorded | Decision reason and immutable receipt | New review required for changed content/context |

## Global rules

- Pending, failed, incomplete, cancelled, timed-out and unauthorised are never rendered as APPROVED.
- Loading, failure and stale states retain submission/review identifiers for support and traceability.
- Provider errors expose safe codes, not raw prompts, credentials or confidential content.
- Use both visible labels and icon/shape; colour alone is insufficient.
