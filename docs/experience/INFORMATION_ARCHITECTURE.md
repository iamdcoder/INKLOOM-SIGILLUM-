# Experience Architecture and Information Architecture

**Design direction:** premium, dark-first editorial assurance instrument; evidence and next action take priority over decoration. Provide a complete light theme. Reviewer Workbench is desktop-first; creator and status flows remain responsive.

## Global application shell

### Persistent shell

- **Workspace / brand selector:** current organisation, workspace and brand; visible scope at all times.
- **Primary navigation:** Overview; Submissions; Review Queue; Brand Control Center; Governance / Impact Radar; Administration / Audit.
- **Global command/search:** search submissions, review IDs, findings and knowledge records within the actor's authorised scope only.
- **Notifications:** assigned reviews, requested changes, job failures, pack approvals and review status changes.
- **User menu:** profile, active role, session and sign out.
- **Context strip:** current brand, channel/locale when relevant, selected Knowledge Pack version and policy version. Never make the governing context implicit.

### Navigation rules

- Navigation visibility is not an authorization mechanism. API/service authorization remains authoritative.
- Preserve deep links to submissions, immutable content versions, review runs, findings, evidence records, patches, decisions and audit receipts.
- Breadcrumbs follow the object path, not just the page name.
- Hide unavailable actions and explain denied actions; never show an enabled control that fails silently.

## Canonical object hierarchy

`Workspace -> Brand -> Submission -> Content Version -> Review Run -> Finding -> Evidence Reference -> Patch -> Decision -> Audit Receipt`

A submission can have multiple immutable content versions. Each review run binds one content hash, one applicable Knowledge Pack version, one policy version, one configuration snapshot and an intended publication context. Findings and decisions belong to that immutable review context.

## Primary information architecture

| Area | Primary user question | Main objects | Primary actions |
|---|---|---|---|
| Overview | What needs attention now? | Submission, job, review, queue item | Filter, open, create submission |
| Submissions | What has been submitted and what version is current? | Submission, content version, parse status | Create, upload, resume, compare history |
| Review Queue | Which assigned items need my decision? | Review, assignment, finding | Claim, assign, inspect, request changes, decide |
| Brand Control Center | What is approved brand truth? | Pack version, fact, policy, term, tone example, asset | Draft, import, validate, compare, submit for owner approval |
| Governance / Impact Radar | Where are recurring risks or unclear policies? | Finding trend, stale source, override, ambiguity cluster | Inspect, propose clarification, enqueue controlled re-review |
| Administration / Audit | Who has access and what happened? | Member, role, configuration, audit event | Invite, disable, assign role, inspect metadata, export authorised audit |

## Role journeys and access boundaries

### Creator

1. Select workspace/brand, channel, locale, audience/scope and intended publication time.
2. Upload supported content and inspect intake/parse state.
3. Open findings; navigate from each finding to its exact text span or image region and source evidence.
4. Accept, edit or reject a proposed patch; inspect diff and regression results.
5. Submit a new immutable version for re-review and track the decision.

**Default restrictions:** cannot approve own submission, change authoritative facts/policies or access another tenant's content.

### Agency / external contributor

1. Open only an assigned brand/campaign context.
2. Upload and review permitted assets using scoped knowledge.
3. Respond to comments, accept/edit/reject permitted patches and download authorised outputs.

**Default restrictions:** cannot browse unrelated brands, private notes or other clients; cannot alter brand truth.

### Reviewer

1. Open assigned queue, sort by risk/age and claim or inspect an item.
2. Inspect finding, exact content location, evidence source/version, scope and validity.
3. Comment, request changes, approve, reject or perform an explicitly authorised override with a mandatory reason.

**Default restrictions:** cannot change policy unless separately assigned Brand Owner privileges; cannot approve a different content hash than the reviewed one.

### Brand Owner

1. Inspect Knowledge Pack draft and source records.
2. Resolve source conflicts, clarify scope/validity and approve a new pack/policy version.
3. Inspect recurring ambiguity, stale facts and override patterns; initiate controlled re-review.

**Default restrictions:** cannot silently rewrite historical approvals; changes create new governing versions.

### Administrator

1. Manage membership, role assignment, session and workspace configuration.
2. Configure retention and provider disclosures; inspect security/audit metadata.

**Default restrictions:** admin privilege alone does not grant approval privilege or unrestricted content access.

### System worker

Runs bounded processing using scoped job context and typed node outputs. It cannot approve, publish, change brand truth, bypass tenant boundaries or execute instructions found inside uploaded content.

## Cross-cutting interaction rules

- Always display the intended publication time, brand/channel scope and pack/policy version used by a review.
- Separate confidence, extraction confidence, evidence sufficiency, verdict and severity.
- A missing/unknown value is not a negative assertion; absence of evidence is not proof of falsity.
- Job failure, timeout, cancellation and provider outage are operational states, never approval states.
- A content edit or governing-context change requires a new review context; history remains reconstructable.
