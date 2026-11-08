# Phase 01 — Experience architecture and visual design system

**Phase objective:** define the interaction model and visual language before implementing each screen.

## Deliverables and current evidence

- [x] Information architecture, global navigation and canonical object path documented.
- [x] Creator, Agency, Reviewer, Brand Owner, Administrator and System Worker journeys documented.
- [x] Eight primary screen specifications and shared-component inventory documented.
- [x] Dark-first design tokens and semantic status conventions documented.
- [x] Loading, empty, error, denied, stale-data, parser-warning, low-confidence OCR and provider-outage state catalogue documented.
- [x] Accessibility design checklist and UX acceptance criteria documented.
- [x] Next.js source implemented for login, overview, submissions/upload, review workbench, Brand Control Center snapshot and audit history.
- [x] Workbench displays backend findings, exact quote/span where available, provenance, scope context, confidence/sufficiency, resolution and version-bound decision controls.
- [ ] Full eight-screen prototype/implementation: Correction Studio, dedicated Reviewer Console, Governance/Impact Radar and Administration settings remain incomplete or embedded/limited.
- [x] Participant Windows frontend dependency installation, lint, typecheck and production build verified on 2026-11-08; preserve the generated package lockfile.
- [ ] Contrast tokens measured and keyboard/responsive walkthrough recorded.

## Acceptance criteria

- [x] A creator can use the implemented UI source to start a submission and inspect the returned review.
- [x] A reviewer can inspect findings and record an authorised decision in the implemented workbench source.
- [x] The Brand Control Center UI shows the current synthetic pack snapshot; full lifecycle governance is not implemented.
- [ ] All critical states are validated in a running browser after frontend build.
- [ ] Accessibility review and responsive walkthrough evidence retained.

## Gate decision

**Gate status: IN PROGRESS.** Product/UX documentation is complete and the core application screens are implemented in source. The core frontend production build has been verified on the participant Windows machine. Dedicated advanced screens, full browser-state walkthrough, formal accessibility validation and responsive walkthrough remain outstanding. Do not claim Phase 01 is fully closed.
