# Inkloom Sigillum

**Brand truth, verified before it ships.**

Inkloom Sigillum is an evidence-first, multimodal, human-governed brand assurance workspace. It checks submitted content against an approved, scoped and time-aware Brand Knowledge Pack. It explains what can be proven, abstains when evidence is insufficient, and leaves consequential decisions to authorised people.

> Project status: Phase 00 foundation pack. No application capability is represented as implemented yet.

## Non-negotiable product invariants

1. **No proof, no SUPPORTED.** A decisive factual verdict requires applicable approved evidence or a deterministic approved rule.
2. **Truth is scoped and time-aware.** Product, offer, geography, audience, channel, locale and intended publication time are part of the truth context.
3. **Workers have no decision rights.** Specialist models propose typed candidates; deterministic policy code adjudicates; authorised humans decide.
4. **Approval is version-bound.** A decision binds to the exact content hash/version, Knowledge Pack and policy versions, evidence snapshot, configuration, reviewer and timestamp.
5. **Failure is never approval.** Parse failure, incomplete extraction, timeout, provider outage, cancellation and exhausted retries remain explicit non-approved states.
6. **History is immutable.** A content edit creates a new version. A policy change creates a new governing context. Historical reviews and decisions are reconstructable.
7. **Every finding has provenance.** Material findings identify the content location and the approved source record/version and applicable context.

## Release discipline

- **Core:** one controlled brand workspace; PDF, DOCX, TXT, PNG and JPG; Knowledge Pack; secure intake; evidence retrieval; claims, terminology, basic tone, OCR-visible text, basic asset and measurable palette/contrast checks; canonical findings; constrained corrections; human approval and audit.
- **Advanced:** richer bitemporal replay, evaluated NLI signal, richer visual-region graph, Impact Radar, policy ambiguity analytics, signed audit checkpoints and bounded policy mutation testing.
- **Stretch / post-event:** PPTX, HTML/email, video captions, CMS/design integrations, private inference, SSO and broader multilingual evaluation.

Do not add advanced features until the Core upload -> evidence -> correction -> approval loop is stable.

## Phase map

| Phase | Outcome |
|---|---|
| 00 | Product contract, scope and build governance |
| 01 | Experience architecture and visual design system |
| 02 | Repository, runtime and engineering foundation |
| 03 | Identity, workspace boundaries and permissions |
| 04 | Brand Control Center and Knowledge Pack lifecycle |
| 05 | Secure submission, storage and immutable content versions |
| 06 | Document parsing, OCR and visual-region extraction |
| 07 | Knowledge normalisation, temporal truth and indexing |
| 08 | Hybrid evidence retrieval and source ranking |
| 09 | Specialist analysis: claims, terminology, tone and visuals |
| 10 | Deterministic adjudication and canonical finding ledger |
| 11 | Durable orchestration, jobs and live progress |
| 12 | Review Workbench, Correction Studio and revision loop |
| 13 | Human approval, audit receipts and policy governance |
| 14 | Impact Radar, governance analytics and policy mutation |
| 15 | Evaluation, security hardening, release and demonstration |

## Planned repository shape

```text
sigillum/
├── apps/
│   ├── web/                         # Next.js App Router experience
│   ├── api/                         # FastAPI application wiring
│   └── worker/                      # Durable worker / LangGraph entry point
├── backend/
│   └── sigillum/
│       ├── domain/                  # Pure entities, value objects, rules, events
│       ├── application/             # Use cases and ports
│       ├── modules/
│       │   ├── identity/            # Membership, RBAC, workspace scope
│       │   ├── knowledge/            # Packs, facts, policies, terms, assets
│       │   ├── content/              # Uploads, immutable versions, extraction
│       │   ├── retrieval/            # Filters, lexical/vector search, RRF
│       │   ├── verification/         # Claims, specialists, adjudicator, findings
│       │   ├── workflow/             # Lifecycle, jobs, checkpoints
│       │   ├── correction/           # Patches, diffs, regression
│       │   └── governance/           # Approvals, audit, impact, policy insights
│       ├── infrastructure/           # DB, storage, OCR, model adapters
│       └── api/                      # Routers, dependencies, schemas
├── packages/contracts/              # OpenAPI-derived TypeScript contracts
├── migrations/                      # Alembic migrations
├── tests/{unit,integration,contract,e2e,security,evaluation}/
├── fixtures/{brand_pack,documents,images,golden_cases,mutations}/
├── docs/{product,requirements,experience,architecture,governance,risks,runbooks,phase-gates}/
├── infra/                           # Docker Compose and deployment config
├── scripts/                         # Reproducible development scripts
├── .env.example
└── README.md
```

## Phase 00 files

- `docs/product/PRODUCT_CHARTER.md` — product contract, boundaries and invariants.
- `docs/requirements/requirements.csv` — traceable requirements with phase, test and UI destination.
- `docs/product/DEMO_SCENARIO.md` — synthetic ORBITA brand and judge-visible anchor scenario.
- `fixtures/brand_pack/v1/` — version-one synthetic Brand Knowledge Pack seed data.
- `fixtures/golden_cases/cases.json` — labelled evaluation cases, including time and evidence edge cases.
- `docs/governance/PROVIDER_REGISTER.csv` — provider disclosure register; providers remain unselected until verified.
- `docs/governance/EVENT_INTEGRITY_CHECKLIST.md` — organiser-rule verification checklist.
- `docs/architecture/ADR-0001-modular-monolith.md` — initial architecture decision record.
- `docs/risks/RISK_REGISTER.csv` — initial risk inventory.
- `docs/phase-gates/PHASE-00-EXIT.md` — Phase 00 acceptance gate.

## Source of truth

`SIGILLUM_Plan` is the master implementation blueprint. The original Devil Union proposal is supporting context. If an implementation choice conflicts with the master plan's invariants or scope, stop and record an ADR before proceeding.


## Official event rules and disclosure

- `docs/governance/OFFICIAL_RULES_EXTRACT.md` — rule summary from the supplied Problem Statement PDF.
- `docs/governance/BUILD_WINDOW_LOG.csv` — event-specific values still requiring organiser confirmation.
- `docs/governance/AI_AND_REUSE_DISCLOSURE.md` — disclosure of pre-window scaffold, synthetic assets, code helper and AI assistance.
- `docs/product/ROUND_SCORING_STRATEGY.md` — evidence strategy aligned to the supplied Round 2 and Round 3 judging rubrics.

## Phase 01 experience documents

- `docs/experience/INFORMATION_ARCHITECTURE.md` — application shell, navigation, object model and access boundaries.
- `docs/experience/ROLE_JOURNEYS.md` — creator, agency, reviewer, owner, administrator and worker journeys.
- `docs/experience/SCREEN_SPECIFICATIONS.md` — eight primary screen contracts.
- `docs/experience/DESIGN_SYSTEM.md` — initial dark/light tokens and semantic state definitions.
- `docs/experience/COMPONENT_CATALOG.md` — shared component inventory.
- `docs/experience/STATE_CATALOG.md` — loading, empty, failure, stale and approval state catalogue.
- `docs/experience/ACCESSIBILITY_CHECKLIST.md` — validation checklist; no conformance claim yet.
- `docs/experience/UX_ACCEPTANCE.md` — user-visible acceptance criteria.

No Next.js, FastAPI, database, worker or adjudication implementation is included. The Phase 00 folder scaffold and fixture helper in the original starter are pre-window materials and must be accurately disclosed if reused.
