# Shared Component Catalogue

Components should be built once with variants; page-specific copies are discouraged.

## Application shell

- `AppShell`, `SidebarNavigation`, `WorkspaceBrandSwitcher`, `GlobalSearch`, `NotificationCentre`, `UserMenu`, `Breadcrumbs`, `PageHeader`, `ContextStrip`.

## Status and risk

- `WorkflowStatusBadge`, `VerdictBadge`, `SeverityBadge`, `AssignmentChip`, `RiskSummary`, `ConfidenceIndicator`, `EvidenceSufficiencyIndicator`, `ExtractionConfidenceNotice`.
- Every component must distinguish verdict, severity, workflow state, model confidence and evidence sufficiency.

## Evidence and knowledge

- `SourceRecordCard`, `SourceVersionLabel`, `ScopeChip`, `ValidityRange`, `OwnerLabel`, `EvidenceSnippet`, `EvidenceInspector`, `PolicyRuleCard`, `KnowledgePackVersionCard`.
- Evidence snippets must display source/version and location; never detach a quote from its source metadata.

## Document and visual review

- `DocumentViewer`, `DocumentToolbar`, `PageThumbnailRail`, `TextSpanHighlight`, `RegionOverlay`, `OCRConfidenceOverlay`, `AssetMatchOverlay`, `FindingNavigator`.
- Viewer coordinate conversion belongs in a tested geometry module, not in styling code.

## Workflow and correction

- `ReviewTimeline`, `AuditEvent`, `CommentThread`, `AssignmentControl`, `DiffViewer`, `PatchPreview`, `RegressionSummary`, `DecisionDialog`, `OverrideReasonForm`.
- Approval actions require server eligibility and explicit confirmation; override requires permission plus reason.

## Data and feedback

- `FilterBar`, `SearchableTable`, `SavedFilter`, `Pagination`, `ChartLegend`, `EmptyState`, `LoadingSkeleton`, `ErrorState`, `PermissionDeniedState`, `StaleContextNotice`, `ParseWarningBanner`, `ProviderOutageBanner`, `Toast`, `RetryAction`.

## Component API principles

- Typed props; no untyped `any` for review, finding, evidence or decision contracts.
- State is explicit: loading, empty, error, disabled, pending and stale are not inferred from missing content.
- Components do not adjudicate claims or decide approval eligibility; those rules belong to backend contracts/services.
- Forms expose validation errors inline and preserve user input on recoverable failures.
- Interactive components support keyboard operation, visible focus and accessible names.
