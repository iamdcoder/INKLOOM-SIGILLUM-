# Accessibility Review Checklist — Design Gate

This is a checklist for validation; no conformance claim is made until measured and tested.

## Keyboard and focus

- [ ] Every critical flow is operable without a pointer.
- [ ] Logical tab order follows the visual/task hierarchy.
- [ ] Focus is visible in both themes and not obscured by sticky panels.
- [ ] Dialogs trap focus appropriately, close predictably and return focus to the trigger.
- [ ] Finding navigation, document page controls, diff review and decision forms have keyboard shortcuts only when discoverable and non-conflicting.

## Semantics and assistive technology

- [ ] Use semantic landmarks, headings, labels, buttons, table headers and status announcements.
- [ ] Icon-only controls have accessible names and tooltips where helpful.
- [ ] Upload progress, job status, validation and decision updates are announced without excessive chatter.
- [ ] Tables and chart legends have text equivalents; colour is not the only encoding.
- [ ] Document-region findings have a textual location and source description, not only a visual overlay.

## Contrast and visual design

- [ ] Measure text and non-text contrast for all final theme/component combinations.
- [ ] Verify status badges, focus rings, selected rows, disabled controls and charts.
- [ ] Ensure zoom/reflow does not hide critical actions or evidence.
- [ ] Avoid tiny metadata for source versions, validity dates and evidence limitations.

## Motion and comprehension

- [ ] Respect reduced-motion preferences.
- [ ] No animation communicates approval before server confirmation.
- [ ] Use plain explanations for verdict, evidence sufficiency, confidence and severity.
- [ ] Long tasks disclose state, retry/cancel behaviour and provider limitations.

## Test evidence to retain

Record browser/OS, assistive technology, keyboard scenario, measured contrast results, findings, fixes and unresolved limitations. Do not mark the design gate complete from checklist authorship alone.
