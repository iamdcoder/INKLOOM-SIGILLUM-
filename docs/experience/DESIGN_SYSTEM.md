# Sigillum Design System — Initial Tokens

**Direction:** calm, precise editorial assurance instrument. Dark-first graphite/navy workspace, restrained teal and indigo accents, solid surfaces for dense evidence, limited translucent overlays. A complete light theme is required.

These are proposed starting tokens. Contrast must be measured on final component combinations before claiming WCAG conformance.

## Colour tokens

### Dark theme

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0B1016` | Application canvas |
| `--surface-1` | `#111923` | Primary panels |
| `--surface-2` | `#172330` | Raised panels / selected rows |
| `--surface-overlay` | `#202D3B` | Menus and floating panels |
| `--border` | `#2D3B49` | Dividers and boundaries |
| `--text-primary` | `#F3F6FA` | Main text |
| `--text-secondary` | `#B3C0CD` | Supporting text |
| `--text-muted` | `#8C9AA8` | Non-critical metadata; never tiny critical text |
| `--accent-primary` | `#55D6C2` | Primary action / active state |
| `--accent-secondary` | `#91A0FF` | Secondary focus / navigation |
| `--danger` | `#FF718B` | Blocking/error |
| `--warning` | `#F5BE55` | Review required / caution |
| `--success` | `#48C99A` | Supported/resolved state |
| `--info` | `#72B7F4` | Informational |

### Light theme

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F5F7FA` | Application canvas |
| `--surface-1` | `#FFFFFF` | Primary panels |
| `--surface-2` | `#EEF2F6` | Raised panels / selected rows |
| `--surface-overlay` | `#FFFFFF` | Menus and floating panels |
| `--border` | `#D5DDE6` | Dividers and boundaries |
| `--text-primary` | `#17212B` | Main text |
| `--text-secondary` | `#465565` | Supporting text |
| `--text-muted` | `#5D6B79` | Non-critical metadata |
| `--accent-primary` | `#087F73` | Primary action / active state |
| `--accent-secondary` | `#4D5FC2` | Secondary focus / navigation |
| `--danger` | `#B4233C` | Blocking/error |
| `--warning` | `#8A5700` | Review required / caution |
| `--success` | `#087B55` | Supported/resolved state |
| `--info` | `#205E9B` | Informational |

## Semantic distinction

- **Verdict:** SUPPORTED, CONTRADICTED, CONFLICTING, STALE, UNVERIFIABLE, NOT_APPLICABLE, NOT_ASSESSED.
- **Severity:** BLOCKING, REVIEW_REQUIRED, SUGGESTION, INFORMATIONAL.
- **Workflow state:** DRAFT, SUBMITTED, QUEUED, INGESTING, ANALYSING, NEEDS_REVIEW, CHANGES_REQUESTED, RESUBMITTED, APPROVED, REJECTED, OVERRIDDEN, PARSE_FAILED, PROVIDER_UNAVAILABLE, TIMED_OUT, CANCELLED, RETRY_EXHAUSTED.
- **Confidence:** extraction/model signal; not a verdict.
- **Evidence sufficiency:** whether available authorised proof covers all material fields; not confidence.

Never use colour alone. Pair semantic colour with text and an icon/shape.

## Typography

- UI/body: Geist Sans or Inter; use one family consistently after dependency/licence check.
- Display/page headings: a restrained editorial serif such as IBM Plex Serif; reserve for page titles and key section headings.
- Technical metadata: JetBrains Mono or system monospace for hashes, IDs, timestamps and code-like values.
- Use tabular numerals for dates, metrics and IDs. Avoid excessive uppercase and tiny metadata.

## Spacing and shape

- Base spacing unit: 4px; primary rhythm: 4 / 8 / 12 / 16 / 24 / 32 / 40 / 48.
- Radius: 6px controls, 10px cards, 14px larger panels; avoid excessive pills.
- Border: 1px neutral by default; use stronger emphasis only for focus, selection or semantic state.
- Elevation: flat surfaces by default; subtle shadow only for popovers/dialogs; use translucency sparingly.

## Motion and responsiveness

- Short transitions for navigation and state changes; no motion that implies certainty or success before server confirmation.
- Respect `prefers-reduced-motion`.
- Desktop-first reviewer workbench; creator submission and status views responsive down to mobile widths.
- Critical actions must remain operable at laptop widths and by keyboard alone.

## Theme and token acceptance

- Verify all foreground/background pairings in both themes.
- Verify focus, hover, pressed, disabled, loading and invalid states.
- Verify status remains understandable in grayscale and with common colour-vision differences.
- Record measured contrast results rather than assuming token combinations pass.
