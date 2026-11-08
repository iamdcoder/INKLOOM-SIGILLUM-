# Synthetic Demo Scenario — ORBITA

> All names, products, offers, facts, logos and examples in this corpus are fictional test data created for Sigillum. They are not claims about a real company.

## Brand

- Brand ID: `brand_orbita_demo`
- Display name: `ORBITA`
- Product: `ORBITA Air One`
- Default locale: `en-IN`
- Geography: `IN`
- Primary channel: `direct_web`
- Pack version: `1.0.0-demo`

## Anchor scenario: the 40% claim

A creator uploads a launch flyer that says **“Saves up to 40% on ORBITA Air One.”** The approved synthetic fact says **“up to 28%”** for the exact offer, product, geography, channel and validity window. The flyer also uses a non-approved logo variant and contains fine print whose measured foreground/background contrast is below the demo policy threshold.

Sigillum must create separate findings for:

1. The unsupported/contradicted saving claim, linked to the exact text span and approved fact.
2. The non-approved logo, linked to the image region and approved asset manifest.
3. The measurable contrast issue, linked to the relevant image region and the configured measurement method.

The creator may accept one patch, reject another, or edit a suggestion. Any accepted change creates a new immutable content version and triggers affected checks again. An authorised reviewer then makes the final decision on that exact version.

## Synthetic approved fact

`FACT-ORBITA-OFFER-001`

- Subject: `ORBITA Air One`
- Predicate: `maximum_saving`
- Value: `28`
- Unit: `%`
- Qualifier: `up_to`
- Offer: `OFFER-ORBITA-OCT-NOV-2026`
- Geography: `IN`
- Channel: `direct_web`
- Valid from: `2026-10-01T00:00:00+05:30`
- Valid until: `2026-11-30T23:59:59+05:30`
- Status: `approved`
- Evidence reference: `SRC-ORBITA-OFFER-TERMS-001`, version `1`

The fact proves only the defined offer and scope. It does not prove a universal saving or any claim for another product, channel, geography or date.

## Required edge-case corpus

| Case ID | Case | Expected handling |
|---|---|---|
| `GOLD-001` | “Saves up to 40%” against the applicable approved 28% fact | Contradicted or policy-defined blocking finding; show exact evidence. |
| `GOLD-002` | “Saves up to 28%” in the exact active scope | Supported only when all material fields and qualifier are proven. |
| `GOLD-003` | Claim relying on an expired offer | Stale / not applicable for the intended publication time. |
| `GOLD-004` | Claim before a future-effective fact begins | Future fact must not be used as current proof. |
| `GOLD-005` | Two equal-authority approved facts overlap and disagree | Conflicting; do not select whichever is retrieved first. |
| `GOLD-006` | Claim has no approved evidence | Unverifiable; unknown is not false. |
| `GOLD-007` | Correct wording but non-approved logo and low-contrast fine print | Separate visual findings with region provenance. |
| `GOLD-008` | OCR text extracted with low confidence | Visible warning/manual review; do not treat uncertain extraction as reliable proof. |
| `GOLD-009` | Malformed or oversized upload | Explicit intake failure; never continue as if clean. |
| `GOLD-010` | Uploaded document contains instructions to reveal secrets or change system behaviour | Treat as untrusted document data; no tool execution or privilege change. |

## Fixture matrix

The event corpus must eventually include PDF, DOCX, TXT, PNG and JPG versions for clean, unsupported-claim, stale-claim, terminology, logo-variant, low-contrast, low-confidence-OCR and malformed/oversized cases. Include positive/negative near-pairs, not only obvious examples.

## Demo success criteria

A judge can upload a realistic asset, inspect every finding's exact location and source, understand evidence sufficiency and uncertainty, accept/edit/reject a constrained correction, see a new immutable version and regression result, and observe an authorised reviewer decision with an audit receipt. No manual database edits are part of the demo path.
