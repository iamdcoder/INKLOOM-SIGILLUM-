"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  BookOpen,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  FileCheck2,
  Fingerprint,
  Globe2,
  History,
  LockKeyhole,
  PackageCheck,
  PencilLine,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  XCircle,
} from "lucide-react";
import {
  api,
  API_BASE,
  getSessionUserRaw,
  getToken,
  parseSessionUser,
  subscribeToSession,
} from "@/lib/api";

type Brand = {
  brand_name: string;
  brand_id: string;
  pack_id: string;
  pack_version: string;
  description: string;
  default_locale: string;
  channels: string[];
  owner_id: string;
  is_synthetic: boolean;
};

type PackSummary = {
  brand: Brand;
  pack_version: string;
  pack_version_id: string;
  knowledge_pack_hash: string;
  policies: number;
  facts: number;
};

type SourceRecord = {
  source_id: string;
  name: string;
  source_type: string;
  version: number;
  status: string;
  sha256?: string | null;
  source_uri?: string | null;
  owner_id?: string;
  approved_by?: string;
  approved_at?: string;
  original_filename?: string;
  storage_key?: string;
  scan_status?: "PENDING" | "CLEAN" | "INFECTED" | "UNAVAILABLE" | "ERROR";
  scan_engine?: string;
  scan_scanned_at?: string | null;
  extraction_status?: string;
  extraction_warnings?: string[];
  region_count?: number;
  reference_text?: string | null;
};

type AssetRecord = {
  asset_id: string;
  name: string;
  kind: string;
  status: string;
  mime_type?: string;
  sha256?: string;
  storage_key?: string;
  width?: number;
  height?: number;
  approved_by?: string;
  scan_status?: "PENDING" | "CLEAN" | "INFECTED" | "UNAVAILABLE" | "ERROR";
  scan_scanned_at?: string | null;
};

type PackSnapshot = {
  brand: Record<string, unknown>;
  facts: unknown[];
  policies: unknown[];
  terminology: Record<string, unknown>;
  voice: Record<string, unknown>;
  assets: Record<string, unknown>;
  sources?: { schema_version: string; sources: SourceRecord[] };
};

type PackVersion = {
  version_id: string;
  pack_version: string;
  fingerprint: string;
  status: string;
  created_at: string;
  created_by: string;
  base_version_id: string | null;
  is_active: boolean;
};

type ManagementPayload = {
  brand: Brand;
  snapshot: PackSnapshot;
  active_version: PackVersion;
  versions: PackVersion[];
  can_edit: boolean;
};

type DraftPayload = {
  draft_id: string;
  base_version_id: string;
  status: string;
  snapshot: PackSnapshot;
};

type VersionComparison = {
  from_version_id: string;
  to_version_id: string;
  change_count: number;
  truncated: boolean;
  changes: Array<{
    section: string;
    record_id: string;
    change: "ADDED" | "REMOVED" | "CHANGED";
    fields: Array<{ field: string; before: string; after: string }>;
    before?: Record<string, unknown>;
    after?: Record<string, unknown>;
  }>;
};

type SourceExtraction = {
  text_characters: number;
  regions_total: number;
  regions_returned: number;
  warnings: string[];
  regions: Array<{ kind?: string; text?: string; page?: number; paragraph?: number }>;
};

type ValidationResult = {
  valid: boolean;
  errors: Array<{ code: string; path: string; message: string }>;
  warnings: Array<{ code: string; path: string; message: string }>;
  validated_at: string;
};

type SectionKey = keyof PackSnapshot;

const SECTIONS: Array<{ key: SectionKey; label: string; description: string }> = [
  { key: "facts", label: "Approved facts", description: "Atomic claims, values, qualifiers, source references and validity." },
  { key: "policies", label: "Policy clauses", description: "Rules, severity, owner, scope and effective dates." },
  { key: "terminology", label: "Terminology", description: "Preferred terms, prohibited variants and scoped exceptions." },
  { key: "voice", label: "Voice guidance", description: "Voice traits, approved examples and disallowed patterns." },
  { key: "assets", label: "Approved assets", description: "Upload, preview and owner-approve brand image assets." },
  { key: "sources", label: "Source registry", description: "Register source evidence, versions, hashes and validity." },
  { key: "brand", label: "Brand identity", description: "Brand metadata, supported channels, locale and workspace identity." },
];

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function shortHash(value: string) {
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "Not available";
}

export default function BrandPage() {
  const sessionSnapshot = useSyncExternalStore(subscribeToSession, getSessionUserRaw, () => null);
  const sessionUser = useMemo(() => parseSessionUser(sessionSnapshot), [sessionSnapshot]);
  const role = sessionUser?.role || "";
  const canViewManagement = ["brand_owner", "reviewer", "administrator"].includes(role);
  const canEdit = role === "brand_owner";

  const [summary, setSummary] = useState<PackSummary | null>(null);
  const [management, setManagement] = useState<ManagementPayload | null>(null);
  const [draft, setDraft] = useState<DraftPayload | null>(null);
  const [activeSection, setActiveSection] = useState<SectionKey>("facts");
  const [editorText, setEditorText] = useState("");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [recordDecisionReason, setRecordDecisionReason] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [sourceType, setSourceType] = useState("reference_text");
  const [sourceText, setSourceText] = useState("");
  const [sourceUri, setSourceUri] = useState("");
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceExtraction, setSourceExtraction] = useState<{ sourceId: string; manifest: SourceExtraction } | null>(null);
  const [compareFrom, setCompareFrom] = useState("");
  const [compareTo, setCompareTo] = useState("");
  const [comparison, setComparison] = useState<VersionComparison | null>(null);
  const [assetName, setAssetName] = useState("");
  const [assetKind, setAssetKind] = useState("logo");
  const [assetFile, setAssetFile] = useState<File | null>(null);
  const [assetPreviews, setAssetPreviews] = useState<Record<string, string>>({});
  const [assetPolicyKind, setAssetPolicyKind] = useState("logo");
  const [assetPolicyChannels, setAssetPolicyChannels] = useState("");
  const [assetPolicyUses, setAssetPolicyUses] = useState("");
  const [assetPolicyMinWidth, setAssetPolicyMinWidth] = useState("0");
  const [assetPolicyMinHeight, setAssetPolicyMinHeight] = useState("0");
  const [assetPolicyPalette, setAssetPolicyPalette] = useState("");
  const [assetPolicyTolerance, setAssetPolicyTolerance] = useState("80");
  const [assetPolicyMatchRatio, setAssetPolicyMatchRatio] = useState("0.7");
  const [assetPolicyClearSpace, setAssetPolicyClearSpace] = useState("0");
  const [assetPolicyValidFrom, setAssetPolicyValidFrom] = useState("");
  const [assetPolicyValidUntil, setAssetPolicyValidUntil] = useState("");

  async function refreshManagement() {
    const [current, detail] = await Promise.all([
      api<PackSummary>("/brands/current"),
      api<ManagementPayload>("/brands/current/management"),
    ]);
    setSummary(current);
    setManagement(detail);
    if (detail.versions.length > 0) {
      const ordered = [...detail.versions].sort((a, b) => a.version_id.localeCompare(b.version_id));
      setCompareTo(detail.active_version.version_id);
      if (ordered.length > 1) setCompareFrom(ordered[ordered.length - 2].version_id);
      else setCompareFrom("");
    }
  }

  useEffect(() => {
    let cancelled = false;
    api<PackSummary>("/brands/current")
      .then((result) => {
        if (!cancelled) setSummary(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load the active Brand Knowledge Pack.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    if (canViewManagement) {
      api<ManagementPayload>("/brands/current/management")
        .then((result) => {
          if (!cancelled) {
            setManagement(result);
            const ordered = [...result.versions].sort((a, b) => a.version_id.localeCompare(b.version_id));
            setCompareTo(result.active_version.version_id);
            if (ordered.length > 1) setCompareFrom(ordered[ordered.length - 2].version_id);
          }
        })
        .catch((reason: unknown) => {
          if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load Knowledge Pack management details.");
        });
    }
    return () => {
      cancelled = true;
    };
  }, [canViewManagement]);

  useEffect(() => {
    let cancelled = false;
    const objectUrls: string[] = [];
    async function loadAssetPreviews() {
      if (!draft || activeSection !== "assets") {
        setAssetPreviews({});
        return;
      }
      const records = ((draft.snapshot.assets.approved_assets as AssetRecord[] | undefined) || [])
        .filter((asset) => asset.storage_key);
      const token = getToken();
      const entries = await Promise.all(records.map(async (asset) => {
        try {
          const response = await fetch(`${API_BASE}/brands/current/drafts/${draft.draft_id}/assets/${asset.asset_id}`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            cache: "no-store",
          });
          if (!response.ok) return [asset.asset_id, ""] as const;
          const url = URL.createObjectURL(await response.blob());
          objectUrls.push(url);
          return [asset.asset_id, url] as const;
        } catch {
          return [asset.asset_id, ""] as const;
        }
      }));
      if (!cancelled) setAssetPreviews(Object.fromEntries(entries.filter((entry) => entry[1])));
    }
    void loadAssetPreviews();
    return () => {
      cancelled = true;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [activeSection, draft]);

  useEffect(() => {
    if (!draft || activeSection !== "assets") return;
    const manifest = draft.snapshot.assets as Record<string, unknown>;
    const policies = (manifest.usage_policies && typeof manifest.usage_policies === "object"
      ? manifest.usage_policies : {}) as Record<string, Record<string, unknown>>;
    const policy = policies[assetPolicyKind] || {};
    setAssetPolicyChannels(Array.isArray(policy.allowed_channels) ? policy.allowed_channels.join(", ") : "");
    setAssetPolicyUses(Array.isArray(policy.allowed_uses) ? policy.allowed_uses.join(", ") : "");
    setAssetPolicyMinWidth(String(policy.min_width ?? 0));
    setAssetPolicyMinHeight(String(policy.min_height ?? 0));
    setAssetPolicyPalette(Array.isArray(policy.palette_hex) ? policy.palette_hex.join(", ") : "");
    setAssetPolicyTolerance(String(policy.palette_tolerance ?? 80));
    setAssetPolicyMatchRatio(String(policy.minimum_palette_match_ratio ?? 0.7));
    setAssetPolicyClearSpace(String(policy.clear_space_ratio ?? 0));
    setAssetPolicyValidFrom(typeof policy.valid_from === "string" ? policy.valid_from.slice(0, 16) : "");
    setAssetPolicyValidUntil(typeof policy.valid_until === "string" ? policy.valid_until.slice(0, 16) : "");
  }, [draft?.draft_id, draft?.snapshot.assets, activeSection, assetPolicyKind]);

  async function saveAssetUsagePolicy() {
    if (!draft) return;
    const splitValues = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);
    const asIso = (value: string) => value ? new Date(value).toISOString() : null;
    const minWidth = Number(assetPolicyMinWidth || 0);
    const minHeight = Number(assetPolicyMinHeight || 0);
    const tolerance = Number(assetPolicyTolerance || 0);
    const matchRatio = Number(assetPolicyMatchRatio || 0);
    const clearSpace = Number(assetPolicyClearSpace || 0);
    if (![minWidth, minHeight, tolerance, matchRatio, clearSpace].every(Number.isFinite)) {
      setError("Asset policy numeric fields must contain valid numbers.");
      return;
    }
    if (assetPolicyValidFrom && assetPolicyValidUntil && new Date(assetPolicyValidUntil) < new Date(assetPolicyValidFrom)) {
      setError("Asset policy end time must not precede its start time.");
      return;
    }
    const currentManifest = draft.snapshot.assets as Record<string, unknown>;
    const existingPolicies = (currentManifest.usage_policies && typeof currentManifest.usage_policies === "object"
      ? currentManifest.usage_policies : {}) as Record<string, unknown>;
    const nextManifest = {
      ...currentManifest,
      usage_policies: {
        ...existingPolicies,
        [assetPolicyKind]: {
          allowed_channels: splitValues(assetPolicyChannels),
          allowed_uses: splitValues(assetPolicyUses),
          min_width: minWidth,
          min_height: minHeight,
          palette_hex: splitValues(assetPolicyPalette).map((value) => value.toUpperCase()),
          palette_tolerance: tolerance,
          minimum_palette_match_ratio: matchRatio,
          clear_space_ratio: clearSpace,
          valid_from: asIso(assetPolicyValidFrom),
          valid_until: asIso(assetPolicyValidUntil),
          severity: "review_required",
        },
      },
    };
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`/brands/current/drafts/${draft.draft_id}/section`, {
        method: "PUT",
        body: JSON.stringify({ section: "assets", content: nextManifest }),
      });
      setDraft((current) => current ? {
        ...current,
        status: "DRAFT",
        snapshot: { ...current.snapshot, assets: nextManifest },
      } : current);
      setEditorText(JSON.stringify(nextManifest, null, 2));
      setValidation(null);
      setNotice(`${assetPolicyKind.replaceAll("_", " ")} usage policy saved to this draft. It will govern only after pack publication.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save the asset usage policy.");
    } finally {
      setBusy(false);
    }
  }

  async function startDraft() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<DraftPayload>("/brands/current/drafts", { method: "POST" });
      setDraft(result);
      setActiveSection("facts");
      setEditorText(JSON.stringify(result.snapshot.facts, null, 2));
      setValidation(null);
      setNotice(`Draft created from ${result.base_version_id}. The active published version remains unchanged.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create a draft.");
    } finally {
      setBusy(false);
    }
  }

  function selectSection(section: SectionKey) {
    if (isEditorDirty && !window.confirm("Discard unsaved edits in this section?")) return;
    setActiveSection(section);
    if (draft) setEditorText(JSON.stringify(draft.snapshot[section], null, 2));
  }

  async function saveSection() {
    if (!draft) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      let content: unknown;
      try {
        content = JSON.parse(editorText) as unknown;
      } catch {
        throw new Error("The editor contains invalid JSON. Correct the syntax before saving.");
      }
      await api(`/brands/current/drafts/${draft.draft_id}/section`, {
        method: "PUT",
        body: JSON.stringify({ section: activeSection, content }),
      });
      setDraft((current) => current ? {
        ...current,
        status: "DRAFT",
        snapshot: { ...current.snapshot, [activeSection]: content } as PackSnapshot,
      } : current);
      setEditorText(JSON.stringify(content, null, 2));
      setValidation(null);
      setNotice(`${SECTIONS.find((section) => section.key === activeSection)?.label || activeSection} saved to the draft. The active pack has not changed.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save this section.");
    } finally {
      setBusy(false);
    }
  }

  async function addSourceRecord() {
    if (!draft) return;
    if (!sourceName.trim() || (!sourceText.trim() && !sourceUri.trim())) {
      setError("Provide a source name and either reference text or an HTTP(S) URI.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ source: SourceRecord }>(`/brands/current/drafts/${draft.draft_id}/sources`, {
        method: "POST",
        body: JSON.stringify({
          name: sourceName.trim(),
          source_type: sourceType,
          version: 1,
          reference_text: sourceText.trim() || null,
          source_uri: sourceUri.trim() || null,
        }),
      });
      const registry = draft.snapshot.sources || { schema_version: "1.0.0", sources: [] };
      const nextRegistry = { ...registry, sources: [...registry.sources, result.source] };
      setDraft((current) => current ? { ...current, status: "DRAFT", snapshot: { ...current.snapshot, sources: nextRegistry } } : current);
      setEditorText(JSON.stringify(nextRegistry, null, 2));
      setSourceName("");
      setSourceText("");
      setSourceUri("");
      setValidation(null);
      setNotice("Source registered in this draft. It remains non-authoritative until approved and the pack is published.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to register the source.");
    } finally {
      setBusy(false);
    }
  }

  async function uploadSourceDocument() {
    if (!draft || !sourceFile) {
      setError("Choose a PDF or DOCX source document before uploading.");
      return;
    }
    if (!sourceName.trim()) {
      setError("Enter a name for the source document.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const form = new FormData();
      form.append("file", sourceFile);
      form.append("name", sourceName.trim());
      form.append("source_type", sourceType);
      form.append("version", "1");
      const result = await api<{ source: SourceRecord }>(`/brands/current/drafts/${draft.draft_id}/sources/upload`, {
        method: "POST",
        body: form,
      });
      const registry = draft.snapshot.sources || { schema_version: "1.0.0", sources: [] };
      const nextRegistry = { ...registry, sources: [...registry.sources, result.source] };
      setDraft((current) => current ? { ...current, status: "DRAFT", snapshot: { ...current.snapshot, sources: nextRegistry } } : current);
      if (activeSection === "sources") setEditorText(JSON.stringify(nextRegistry, null, 2));
      setSourceFile(null);
      setSourceName("");
      setValidation(null);
      setNotice(result.source.scan_status === "CLEAN"
        ? "Source uploaded, malware-scanned and extracted. It is still non-authoritative until owner approval and pack publication."
        : `Source uploaded to quarantine. Scanner status: ${result.source.scan_status || "PENDING"}. It cannot be approved or downloaded until scanning succeeds.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to upload the source document.");
    } finally {
      setBusy(false);
    }
  }

  async function rescanSourceDocument(sourceId: string) {
    if (!draft) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ scan_status: string; extraction_status: string }>(
        `/brands/current/drafts/${draft.draft_id}/sources/${sourceId}/scan`, { method: "POST" },
      );
      const latest = await api<DraftPayload>(`/brands/current/drafts/${draft.draft_id}`);
      setDraft(latest);
      setEditorText(JSON.stringify(latest.snapshot[activeSection] ?? {}, null, 2));
      setValidation(null);
      setNotice(`Source scan: ${result.scan_status}. Extraction: ${result.extraction_status}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to rescan this source document.");
    } finally {
      setBusy(false);
    }
  }

  async function openSourceExtraction(sourceId: string) {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const manifest = await api<SourceExtraction>(`/brands/current/drafts/${draft.draft_id}/sources/${sourceId}/extraction`);
      setSourceExtraction({ sourceId, manifest });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to open extracted source text.");
    } finally {
      setBusy(false);
    }
  }

  async function downloadSourceDocument(source: SourceRecord) {
    if (!draft) return;
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE}/brands/current/drafts/${draft.draft_id}/sources/${source.source_id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`Download failed (${response.status}). The source may still be quarantined.`);
      const objectUrl = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = source.original_filename || `${source.name}.bin`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to download this source document.");
    }
  }

  async function comparePublishedVersions() {
    if (!compareFrom || !compareTo || compareFrom === compareTo) {
      setError("Choose two different published versions to compare.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const query = new URLSearchParams({ from_version_id: compareFrom, to_version_id: compareTo });
      const result = await api<VersionComparison>(`/brands/current/versions/compare?${query.toString()}`);
      setComparison(result);
      setNotice(`${result.change_count} change(s) found between ${compareFrom} and ${compareTo}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to compare the selected published versions.");
    } finally {
      setBusy(false);
    }
  }

  async function rescanBrandAsset(assetId: string) {
    if (!draft) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ scan_status: string }>(`/brands/current/drafts/${draft.draft_id}/assets/${assetId}/scan`, { method: "POST" });
      const latest = await api<DraftPayload>(`/brands/current/drafts/${draft.draft_id}`);
      setDraft(latest);
      setEditorText(JSON.stringify(latest.snapshot[activeSection] ?? {}, null, 2));
      setValidation(null);
      setNotice(`Asset malware scan status: ${result.scan_status}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to rescan this asset.");
    } finally {
      setBusy(false);
    }
  }

  async function uploadBrandAsset() {
    if (!draft || !assetFile) {
      setError("Choose a PNG, JPEG or WebP image before uploading.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const form = new FormData();
      form.append("file", assetFile);
      form.append("name", assetName.trim() || assetFile.name);
      form.append("kind", assetKind);
      const result = await api<{ asset: AssetRecord }>(`/brands/current/drafts/${draft.draft_id}/assets`, {
        method: "POST",
        body: form,
      });
      const currentAssets = (draft.snapshot.assets.approved_assets as AssetRecord[] | undefined) || [];
      const nextAssets = { ...draft.snapshot.assets, approved_assets: [...currentAssets, result.asset] };
      setDraft((current) => current ? {
        ...current,
        status: "DRAFT",
        snapshot: { ...current.snapshot, assets: nextAssets },
      } : current);
      if (activeSection === "assets") setEditorText(JSON.stringify(nextAssets, null, 2));
      setAssetFile(null);
      setAssetName("");
      setValidation(null);
      setNotice("Asset uploaded privately as a draft record. A Brand Owner must explicitly approve it before publication.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to upload the brand asset.");
    } finally {
      setBusy(false);
    }
  }

  async function decideKnowledgeRecord(
    recordType: "fact" | "policy" | "term" | "source" | "asset",
    recordId: string,
    status: "approved" | "rejected",
  ) {
    if (!draft) return;
    const reasonText = recordDecisionReason.trim();
    if (!reasonText) {
      setError("Enter a reason before recording a Knowledge Pack decision.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`/brands/current/drafts/${draft.draft_id}/records/${recordType}/${recordId}/decision`, {
        method: "POST",
        body: JSON.stringify({ status, reason: reasonText }),
      });
      const latest = await api<DraftPayload>(`/brands/current/drafts/${draft.draft_id}`);
      setDraft(latest);
      setEditorText(JSON.stringify(latest.snapshot[activeSection] ?? {}, null, 2));
      setValidation(null);
      setRecordDecisionReason("");
      const label = ({ fact: "Fact", policy: "Policy", term: "Terminology", source: "Source", asset: "Asset" } as const)[recordType];
      setNotice(`${label} ${status === "approved" ? "approved" : "rejected"} in the draft. The change becomes authoritative only after pack publication.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update this record decision.");
    } finally {
      setBusy(false);
    }
  }

  async function validateDraft() {
    if (!draft) return;
    if (isEditorDirty) {
      setError("Save the current section before validating the draft.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<ValidationResult>(`/brands/current/drafts/${draft.draft_id}/validate`, { method: "POST" });
      setValidation(result);
      setDraft((current) => current ? { ...current, status: result.valid ? "VALIDATED" : "DRAFT" } : current);
      if (result.valid) setNotice("Validation passed. The draft is eligible for Brand Owner publication.");
      else setError(`Validation found ${result.errors.length} issue(s). Review the error list before publishing.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to validate the draft.");
    } finally {
      setBusy(false);
    }
  }

  async function publishDraft() {
    if (!draft || !validation?.valid) return;
    const confirmed = window.confirm("Publish this validated Brand Knowledge Pack? New reviews will use it. Existing review snapshots remain unchanged.");
    if (!confirmed) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<PackVersion>(`/brands/current/drafts/${draft.draft_id}/publish`, { method: "POST" });
      setNotice(`Published ${result.pack_version} (${result.version_id}). New reviews will use this pack version.`);
      setDraft(null);
      setValidation(null);
      await refreshManagement();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Publication failed. The active version was not confirmed as changed.");
    } finally {
      setBusy(false);
    }
  }

  const sectionDescription = SECTIONS.find((section) => section.key === activeSection)?.description;
  const isEditorDirty = draft ? editorText !== JSON.stringify(draft.snapshot[activeSection], null, 2) : false;
  const activeFacts = Array.isArray(management?.snapshot.facts) ? management.snapshot.facts.length : summary?.facts ?? 0;
  const activePolicies = Array.isArray(management?.snapshot.policies) ? management.snapshot.policies.length : summary?.policies ?? 0;
  const draftSources = draft?.snapshot.sources?.sources || [];
  const draftAssets = ((draft?.snapshot.assets.approved_assets as AssetRecord[] | undefined) || []);
  const draftFacts = (draft?.snapshot.facts || []) as Array<Record<string, unknown> & { fact_id?: string; status?: string }> ;
  const draftPolicies = (draft?.snapshot.policies || []) as Array<Record<string, unknown> & { policy_id?: string; name?: string; status?: string }> ;
  const terminology = draft?.snapshot.terminology || {};
  const draftTerms = [
    ...((terminology.preferred_terms as Array<Record<string, unknown> & { term_id?: string; preferred?: string; status?: string }> | undefined) || []),
    ...((terminology.prohibited_or_review_terms as Array<Record<string, unknown> & { term_id?: string; variant?: string; status?: string }> | undefined) || []),
  ];

  return (
    <div className="page-stack">
      <section className="hero-row">
        <div>
          <div className="eyebrow">BRAND GOVERNANCE</div>
          <h1>Brand Control Center</h1>
          <p className="subhead">One approved, scoped and time-aware source of brand truth.</p>
        </div>
        <span className="status-pill success"><i /> ACTIVE KNOWLEDGE PACK</span>
      </section>

      {error && <div className="alert error" role="alert"><CircleAlert size={15} />{error}</div>}
      {notice && <div className="alert info" role="status"><CheckCircle2 size={15} />{notice}</div>}
      {loading && <div className="panel panel-loading">Loading the active Brand Knowledge Pack…</div>}

      {summary && (
        <>
          <section className="brand-banner">
            <div className="brand-monogram">{summary.brand.brand_name.slice(0, 1)}</div>
            <div>
              <div className="eyebrow">ACTIVE BRAND KNOWLEDGE PACK</div>
              <h2>{summary.brand.brand_name}</h2>
              <p>{summary.brand.description}</p>
              <div className="brand-tags">
                <span><Globe2 size={13} /> {summary.brand.default_locale}</span>
                <span><CalendarClock size={13} /> {summary.pack_version}</span>
                <span><ShieldCheck size={13} /> Owner controlled</span>
                {summary.brand.is_synthetic && <span><Sparkles size={13} /> Synthetic demo data</span>}
              </div>
            </div>
            <div className="pack-id"><small>PACK ID</small><b>{summary.brand.pack_id}</b></div>
          </section>

          <div className="metric-grid two-metrics">
            <article className="metric-card"><div className="metric-top"><span>FACT RECORDS</span><FileCheck2 size={17} /></div><strong>{activeFacts}</strong><small>Scoped facts and claims</small></article>
            <article className="metric-card"><div className="metric-top"><span>POLICY CLAUSES</span><BookOpen size={17} /></div><strong>{activePolicies}</strong><small>Versioned policy rules</small></article>
          </div>

          <section className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading"><div><div className="eyebrow">KNOWLEDGE PACK STRUCTURE</div><h2>Authoritative record classes</h2></div><PackageCheck size={18} /></div>
              {SECTIONS.filter((section) => section.key !== "brand").map((section) => (
                <div className="pack-row" key={section.key}>
                  <div className="pack-row-icon">{section.key === "facts" ? <FileCheck2 size={18} /> : section.key === "policies" ? <BookOpen size={18} /> : section.key === "assets" ? <ShieldCheck size={18} /> : <ClipboardCheck size={18} />}</div>
                  <div><b>{section.label}</b><small>{section.description}</small></div>
                  <CheckCircle2 size={16} className="text-green" />
                </div>
              ))}
            </section>
            <section className="panel">
              <div className="eyebrow">ACTIVE GOVERNANCE CONTEXT</div>
              <h2>Publication boundaries</h2>
              <p className="panel-description">A fact is eligible only when its approval, context and validity match the intended publication.</p>
              <div className="scope-list">{summary.brand.channels.map((channel) => <span key={channel}>{channel.replaceAll("_", " ")}</span>)}</div>
              <div className="context-row"><span>Locale</span><b>{summary.brand.default_locale}</b></div>
              <div className="context-row"><span>Owner</span><b>{summary.brand.owner_id}</b></div>
              <div className="context-row"><span>Brand ID</span><b>{summary.brand.brand_id}</b></div>
              <div className="context-row"><span>Active version</span><b>{summary.pack_version_id}</b></div>
              <div className="context-row"><span>Pack fingerprint</span><b className="hash-value">{shortHash(summary.knowledge_pack_hash)}</b></div>
            </section>
          </section>
        </>
      )}

      {canViewManagement && management && (
        <section className="panel knowledge-version-panel">
          <div className="panel-heading">
            <div><div className="eyebrow">VERSION GOVERNANCE</div><h2>Published Knowledge Pack history</h2></div>
            <History size={18} />
          </div>
          <div className="knowledge-version-list">
            {management.versions.map((version) => (
              <div className="knowledge-version-row" key={version.version_id}>
                <div className="version-history-mark"><Fingerprint size={15} /></div>
                <div className="knowledge-version-copy"><b>{version.pack_version} <span>{version.version_id}</span></b><small>{formatDate(version.created_at)} · by {version.created_by}</small><small>SHA-256: {shortHash(version.fingerprint)}</small></div>
                <span className={`status-pill ${version.is_active ? "success" : "neutral"}`}><i />{version.is_active ? "ACTIVE" : "PUBLISHED"}</span>
              </div>
            ))}
          </div>
          {management.versions.length > 1 && (
            <div className="knowledge-comparison">
              <div className="eyebrow">IMMUTABLE VERSION COMPARISON</div>
              <div className="knowledge-guided-grid">
                <label>From version<select value={compareFrom} onChange={(event) => setCompareFrom(event.target.value)}>
                  {management.versions.map((version) => <option key={version.version_id} value={version.version_id}>{version.pack_version} · {version.version_id}</option>)}
                </select></label>
                <label>To version<select value={compareTo} onChange={(event) => setCompareTo(event.target.value)}>
                  {management.versions.map((version) => <option key={version.version_id} value={version.version_id}>{version.pack_version} · {version.version_id}</option>)}
                </select></label>
              </div>
              <button className="button secondary" onClick={comparePublishedVersions} disabled={busy || !compareFrom || !compareTo || compareFrom === compareTo}>Compare published versions</button>
              {comparison && <div className="knowledge-record-list">
                <p className="knowledge-guided-note">{comparison.change_count} record-level change(s){comparison.truncated ? " · results truncated at the safety limit" : ""}.</p>
                {comparison.changes.map((change, index) => (
                  <div className="knowledge-comparison-row" key={`${change.section}-${change.record_id}-${index}`}>
                    <b>{change.section} · {change.record_id}</b><span className="status-pill neutral"><i />{change.change}</span>
                    {change.fields.map((field) => <small key={field.field}><b>{field.field}</b>: {field.before || "(empty)"} → {field.after || "(empty)"}</small>)}
                    {change.change === "ADDED" && <small>New record: {JSON.stringify(change.after)}</small>}
                    {change.change === "REMOVED" && <small>Removed record: {JSON.stringify(change.before)}</small>}
                  </div>
                ))}
                {comparison.changes.length === 0 && <p className="knowledge-guided-empty">No differences were found between these versions.</p>}
              </div>}
            </div>
          )}
          {!canEdit && <div className="alert info knowledge-readonly"><LockKeyhole size={14} /> You can inspect published versions. Only the Brand Owner can change and publish authoritative brand truth.</div>}
        </section>
      )}

      {canEdit && management && (
        <section className="panel knowledge-editor-panel">
          <div className="panel-heading knowledge-editor-heading">
            <div><div className="eyebrow">OWNER WORKSPACE</div><h2>Knowledge Pack editor</h2><p className="panel-description">Changes are isolated in a draft. Published versions remain immutable until validation and explicit publication.</p></div>
            {!draft ? (
              <button className="button primary" onClick={startDraft} disabled={busy}><Plus size={15} /> Create draft</button>
            ) : (
              <span className={`status-pill ${draft.status === "VALIDATED" ? "success" : "warning"}`}><i /> {draft.status}</span>
            )}
          </div>

          {!draft ? (
            <div className="knowledge-empty"><PencilLine size={22} /><b>No draft in progress</b><span>Create a draft from the active published version to propose changes. Nothing becomes authoritative until you validate and publish it.</span></div>
          ) : (
            <>
              <div className="draft-context"><div><small>DRAFT ID</small><b>{draft.draft_id}</b></div><div><small>BASED ON</small><b>{draft.base_version_id}</b></div><div><small>ACTIVE VERSION</small><b>{management.active_version.version_id}</b></div></div>
              <div className="knowledge-editor-layout">
                <nav className="knowledge-section-nav" aria-label="Knowledge Pack sections">
                  {SECTIONS.map((section) => (
                    <button key={section.key} className={activeSection === section.key ? "selected" : ""} onClick={() => selectSection(section.key)}><span>{section.label}</span><ChevronRight size={14} /></button>
                  ))}
                </nav>
                <div className="knowledge-editor-main">
                  <div className="knowledge-editor-toolbar"><div><b>{SECTIONS.find((section) => section.key === activeSection)?.label}</b><small>{sectionDescription}</small></div><span>{isEditorDirty ? "UNSAVED" : "JSON"}</span></div>
                  {["facts", "policies", "terminology", "sources", "assets"].includes(activeSection) && (
                    <label className="knowledge-decision-reason">Decision reason<input value={recordDecisionReason} onChange={(event) => setRecordDecisionReason(event.target.value)} maxLength={1000} placeholder="Explain why this record is approved or rejected." /></label>
                  )}
                  {activeSection === "facts" && (
                    <div className="knowledge-guided-panel">
                      <div className="eyebrow">FACT APPROVAL REGISTER</div>
                      <p className="knowledge-guided-note">Only facts with approved, version-matched source evidence can pass publication validation. Draft facts are never authoritative.</p>
                      <div className="knowledge-record-list">
                        {draftFacts.map((fact, index) => {
                          const id = String(fact.fact_id || `fact-${index}`);
                          const status = String(fact.status || "draft");
                          return (
                            <div className="knowledge-record-row" key={id}>
                              <div><b>{String(fact.subject || id)}</b><small>{id} · {String(fact.predicate || "Unspecified predicate")}</small><small>{String(fact.qualifier || "")}{fact.value !== undefined ? ` ${String(fact.value)}${String(fact.unit || "")}` : ""} · source {String((fact.source_ref as Record<string, unknown> | undefined)?.source_id || "not linked")}</small></div>
                              <span className={`status-pill ${status === "approved" ? "success" : "warning"}`}><i />{status}</span>
                              {status !== "approved" && <button className="button secondary" onClick={() => decideKnowledgeRecord("fact", id, "approved")} disabled={busy}>Approve</button>}
                              {status !== "rejected" && <button className="button secondary" onClick={() => decideKnowledgeRecord("fact", id, "rejected")} disabled={busy}>Reject</button>}
                            </div>
                          );
                        })}
                        {draftFacts.length === 0 && <p className="knowledge-guided-empty">No facts have been registered for this brand.</p>}
                      </div>
                    </div>
                  )}
                  {activeSection === "policies" && (
                    <div className="knowledge-guided-panel">
                      <div className="eyebrow">POLICY APPROVAL REGISTER</div>
                      <p className="knowledge-guided-note">Policy rules and severity are owner-governed. Rejected or draft policies do not govern a published pack.</p>
                      <div className="knowledge-record-list">
                        {draftPolicies.map((policy, index) => {
                          const id = String(policy.policy_id || `policy-${index}`);
                          const status = String(policy.status || "draft");
                          return (
                            <div className="knowledge-record-row" key={id}>
                              <div><b>{String(policy.name || id)}</b><small>{id} · {String(policy.category || "uncategorised")} · {String(policy.severity || "no severity")}</small><small>{String(policy.rule || "No policy rule text")}</small></div>
                              <span className={`status-pill ${status === "approved" ? "success" : "warning"}`}><i />{status}</span>
                              {status !== "approved" && <button className="button secondary" onClick={() => decideKnowledgeRecord("policy", id, "approved")} disabled={busy}>Approve</button>}
                              {status !== "rejected" && <button className="button secondary" onClick={() => decideKnowledgeRecord("policy", id, "rejected")} disabled={busy}>Reject</button>}
                            </div>
                          );
                        })}
                        {draftPolicies.length === 0 && <p className="knowledge-guided-empty">No policies have been registered for this brand.</p>}
                      </div>
                    </div>
                  )}
                  {activeSection === "terminology" && (
                    <div className="knowledge-guided-panel">
                      <div className="eyebrow">TERMINOLOGY APPROVAL REGISTER</div>
                      <p className="knowledge-guided-note">Canonical terms and prohibited variants are kept distinct from factual evidence. Owner decisions apply only after publication.</p>
                      <div className="knowledge-record-list">
                        {draftTerms.map((term, index) => {
                          const id = String(term.term_id || `term-${index}`);
                          const status = String(term.status || "draft");
                          const termText = String(term.preferred || term.variant || id);
                          return (
                            <div className="knowledge-record-row" key={id}>
                              <div><b>{termText}</b><small>{id} · {term.preferred ? "Preferred" : "Prohibited / review"} · {String(term.locale || "all locales")}</small><small>{String(term.reason || "")}</small></div>
                              <span className={`status-pill ${status === "approved" ? "success" : "warning"}`}><i />{status}</span>
                              {status !== "approved" && <button className="button secondary" onClick={() => decideKnowledgeRecord("term", id, "approved")} disabled={busy}>Approve</button>}
                              {status !== "rejected" && <button className="button secondary" onClick={() => decideKnowledgeRecord("term", id, "rejected")} disabled={busy}>Reject</button>}
                            </div>
                          );
                        })}
                        {draftTerms.length === 0 && <p className="knowledge-guided-empty">No terminology records have been registered for this brand.</p>}
                      </div>
                    </div>
                  )}
                  {activeSection === "sources" && (
                    <div className="knowledge-guided-panel">
                      <div className="eyebrow">REGISTER EVIDENCE SOURCE</div>
                      <p className="knowledge-guided-note">Source URLs are recorded as provenance metadata and are never fetched automatically. Paste the exact authorised excerpt needed for evidence review.</p>
                      <div className="knowledge-guided-grid">
                        <label>Source name<input value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder="Official product specification" maxLength={240} /></label>
                        <label>Source type<select value={sourceType} onChange={(event) => setSourceType(event.target.value)}><option value="reference_text">Reference text</option><option value="product_specification">Product specification</option><option value="campaign_terms">Campaign terms</option><option value="policy_document">Policy document</option><option value="guideline">Brand guideline</option><option value="other">Other</option></select></label>
                        <label className="wide">Reference excerpt<textarea value={sourceText} onChange={(event) => setSourceText(event.target.value)} rows={3} maxLength={20000} placeholder="Paste the exact approved excerpt that can substantiate a fact or rule." /></label>
                        <label className="wide">Source URI (optional)<input value={sourceUri} onChange={(event) => setSourceUri(event.target.value)} placeholder="https://..." maxLength={2048} /></label>
                      </div>
                      <button className="button secondary" onClick={addSourceRecord} disabled={busy}><Plus size={14} /> Register source as draft</button>
                      <div className="knowledge-source-upload">
                        <div className="eyebrow">CONTROLLED DOCUMENT INTAKE</div>
                        <p className="knowledge-guided-note">PDF and DOCX uploads are stored privately, malware-scanned before parsing, and kept non-authoritative until explicit owner approval and publication. Scanner outage leaves the file quarantined.</p>
                        <label>PDF or DOCX source file<input type="file" accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx" onChange={(event) => setSourceFile(event.target.files?.[0] || null)} /></label>
                        <button className="button secondary" onClick={uploadSourceDocument} disabled={busy || !sourceFile || !sourceName.trim()}><UploadCloud size={14} /> Upload and scan source</button>
                      </div>
                      <div className="knowledge-record-list">
                        {draftSources.map((source) => (
                          <div className="knowledge-record-row" key={source.source_id}>
                            <div><b>{source.name}</b><small>{source.source_id} · v{source.version} · {source.source_type}</small><small>{source.sha256 ? `SHA-256 ${shortHash(source.sha256)}` : source.source_uri || "Reference text retained in registry"}</small>
                              {source.storage_key && <small>Malware scan: {source.scan_status || "PENDING"} · extraction: {source.extraction_status || "PENDING"} · {source.region_count || 0} region(s)</small>}
                              {(source.extraction_warnings || []).map((warning) => <small className="text-warning" key={warning}>{warning}</small>)}
                            </div>
                            <span className={`status-pill ${source.status === "approved" ? "success" : "warning"}`}><i />{source.status}</span>
                            {source.storage_key && <span className={`status-pill ${source.scan_status === "CLEAN" ? "success" : "warning"}`}><i />{source.scan_status || "PENDING"}</span>}
                            {source.storage_key && source.scan_status !== "CLEAN" && <button className="button secondary" onClick={() => rescanSourceDocument(source.source_id)} disabled={busy}>Retry scan</button>}
                            {source.storage_key && source.scan_status === "CLEAN" && <><button className="button secondary" onClick={() => openSourceExtraction(source.source_id)} disabled={busy}>View extraction</button><button className="button secondary" onClick={() => downloadSourceDocument(source)}>Download</button></>}
                            {source.status !== "approved" && <button className="button secondary" onClick={() => decideKnowledgeRecord("source", source.source_id, "approved")} disabled={busy || Boolean(source.storage_key && (source.scan_status !== "CLEAN" || source.extraction_status !== "COMPLETED"))}>Approve</button>}
                            {source.status !== "rejected" && <button className="button secondary" onClick={() => decideKnowledgeRecord("source", source.source_id, "rejected")} disabled={busy}>Reject</button>}
                          </div>
                        ))}
                        {draftSources.length === 0 && <p className="knowledge-guided-empty">No sources registered in this draft yet.</p>}
                      </div>
                      {sourceExtraction && <div className="knowledge-source-extraction">
                        <div className="knowledge-editor-toolbar"><b>Extracted source regions · {sourceExtraction.sourceId}</b><button className="button secondary" onClick={() => setSourceExtraction(null)}>Close</button></div>
                        <p className="knowledge-guided-note">{sourceExtraction.manifest.text_characters} characters · {sourceExtraction.manifest.regions_returned}/{sourceExtraction.manifest.regions_total} regions retained.</p>
                        {sourceExtraction.manifest.regions.map((region, index) => <div className="source-extraction-region" key={`${sourceExtraction.sourceId}-${index}`}><small>{region.kind || "TEXT"}{region.page ? ` · page ${region.page}` : ""}{region.paragraph ? ` · paragraph ${region.paragraph}` : ""}</small><p>{region.text || "(no text)"}</p></div>)}
                        {sourceExtraction.manifest.warnings.map((warning) => <small className="text-warning" key={warning}>{warning}</small>)}
                      </div>}
                    </div>
                  )}
                  {activeSection === "assets" && (
                    <div className="knowledge-guided-panel">
                      <div className="eyebrow">OWNER-CONFIGURED ASSET USAGE POLICY</div>
                      <p className="knowledge-guided-note">Set channel/use restrictions, minimum pixel dimensions, approved palette tolerance, clear-space requirement and validity. Palette is a bounded RGB estimate; clear-space always remains a human inspection.</p>
                      <div className="knowledge-guided-grid">
                        <label>Asset kind<select value={assetPolicyKind} onChange={(event) => setAssetPolicyKind(event.target.value)}><option value="logo">Logo</option><option value="product_image">Product image</option><option value="campaign_image">Campaign image</option><option value="icon">Icon</option><option value="other">Other</option></select></label>
                        <label>Allowed channels (comma-separated)<input value={assetPolicyChannels} onChange={(event) => setAssetPolicyChannels(event.target.value)} placeholder="direct_web, social" /></label>
                        <label className="wide">Allowed uses (comma-separated)<input value={assetPolicyUses} onChange={(event) => setAssetPolicyUses(event.target.value)} placeholder="brand_lockup, campaign, social_ad" /></label>
                        <label>Minimum width (px)<input type="number" min="0" max="20000" value={assetPolicyMinWidth} onChange={(event) => setAssetPolicyMinWidth(event.target.value)} /></label>
                        <label>Minimum height (px)<input type="number" min="0" max="20000" value={assetPolicyMinHeight} onChange={(event) => setAssetPolicyMinHeight(event.target.value)} /></label>
                        <label className="wide">Approved palette hex colours<input value={assetPolicyPalette} onChange={(event) => setAssetPolicyPalette(event.target.value)} placeholder="#123ABC, #F0F0F0" /></label>
                        <label>RGB tolerance (0–441.7)<input type="number" min="0" max="441.7" step="0.1" value={assetPolicyTolerance} onChange={(event) => setAssetPolicyTolerance(event.target.value)} /></label>
                        <label>Minimum palette match (0–1)<input type="number" min="0" max="1" step="0.05" value={assetPolicyMatchRatio} onChange={(event) => setAssetPolicyMatchRatio(event.target.value)} /></label>
                        <label>Clear-space ratio (0–0.5)<input type="number" min="0" max="0.5" step="0.01" value={assetPolicyClearSpace} onChange={(event) => setAssetPolicyClearSpace(event.target.value)} /></label>
                        <label>Valid from<input type="datetime-local" value={assetPolicyValidFrom} onChange={(event) => setAssetPolicyValidFrom(event.target.value)} /></label>
                        <label>Valid until<input type="datetime-local" value={assetPolicyValidUntil} onChange={(event) => setAssetPolicyValidUntil(event.target.value)} /></label>
                      </div>
                      <button className="button secondary" onClick={saveAssetUsagePolicy} disabled={busy}><Save size={14} /> Save usage policy to draft</button>
                      <div className="eyebrow">UPLOAD BRAND ASSET</div>
                      <div className="knowledge-guided-grid">
                        <label>Display name<input value={assetName} onChange={(event) => setAssetName(event.target.value)} placeholder="Primary campaign logo" maxLength={160} /></label>
                        <label>Asset type<select value={assetKind} onChange={(event) => setAssetKind(event.target.value)}><option value="logo">Logo</option><option value="product_image">Product image</option><option value="campaign_image">Campaign image</option><option value="icon">Icon</option><option value="other">Other</option></select></label>
                        <label className="wide">Image file<input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setAssetFile(event.target.files?.[0] || null)} /></label>
                      </div>
                      <p className="knowledge-guided-note">PNG, JPEG or WebP only. SVG/script-bearing files are rejected. Uploads remain private and unapproved until an owner decision. Raster decoding, size checks and fail-closed malware scanning are applied.</p>
                      <button className="button secondary" onClick={uploadBrandAsset} disabled={busy || !assetFile}><UploadCloud size={14} /> Upload as draft asset</button>
                      <div className="knowledge-record-list">
                        {draftAssets.map((asset) => (
                          <div className="knowledge-record-row asset-row" key={asset.asset_id}>
                            {assetPreviews[asset.asset_id] ? <img src={assetPreviews[asset.asset_id]} alt={`Preview of ${asset.name}`} /> : <div className="knowledge-asset-placeholder"><ShieldCheck size={17} /></div>}
                            <div><b>{asset.name}</b><small>{asset.asset_id} · {asset.kind} · {asset.mime_type || "legacy asset"}</small><small>{asset.sha256 ? `SHA-256 ${shortHash(asset.sha256)}` : "Seeded asset record"}</small></div>
                            <span className={`status-pill ${asset.status === "approved" ? "success" : "warning"}`}><i />{asset.status}</span>
                            {asset.storage_key && <span className={`status-pill ${asset.scan_status === "CLEAN" ? "success" : "warning"}`}><i />{asset.scan_status || "PENDING"}</span>}
                            {asset.storage_key && asset.scan_status !== "CLEAN" && <button className="button secondary" onClick={() => rescanBrandAsset(asset.asset_id)} disabled={busy}>Retry scan</button>}
                            {asset.status !== "approved" && <button className="button secondary" onClick={() => decideKnowledgeRecord("asset", asset.asset_id, "approved")} disabled={busy || !asset.storage_key || asset.scan_status !== "CLEAN"}>Approve</button>}
                            {asset.status !== "rejected" && <button className="button secondary" onClick={() => decideKnowledgeRecord("asset", asset.asset_id, "rejected")} disabled={busy}>Reject</button>}
                          </div>
                        ))}
                        {draftAssets.length === 0 && <p className="knowledge-guided-empty">No assets registered in this draft yet.</p>}
                      </div>
                    </div>
                  )}
                  <label className="visually-hidden" htmlFor="knowledge-pack-json">Edit {activeSection} JSON</label>
                  <textarea id="knowledge-pack-json" className="knowledge-json-editor" spellCheck={false} value={editorText} onChange={(event) => { setEditorText(event.target.value); setValidation(null); }} />
                  <div className="knowledge-editor-actions"><span>Save updates this draft only. It does not change the active pack.</span><button className="button secondary" onClick={saveSection} disabled={busy || !isEditorDirty}><Save size={14} /> Save section</button></div>
                </div>
              </div>

              {validation && (
                <div className={`knowledge-validation ${validation.valid ? "valid" : "invalid"}`}>
                  <div className="knowledge-validation-title">{validation.valid ? <CheckCircle2 size={16} /> : <XCircle size={16} />}<b>{validation.valid ? "Validation passed" : `Validation failed · ${validation.errors.length} issue(s)`}</b></div>
                  {validation.errors.map((item, index) => <div className="knowledge-validation-item" key={`${item.code}-${index}`}><b>{item.code}</b><span>{item.path}</span><p>{item.message}</p></div>)}
                  {validation.valid && <p className="knowledge-validation-note">The draft passed structural and consistency checks. Publication still requires your explicit confirmation.</p>}
                </div>
              )}

              <div className="knowledge-publish-actions">
                <span><LockKeyhole size={14} /> Publishing creates a new immutable version and changes the pack used by future reviews.</span>
                <div><button className="button secondary" onClick={validateDraft} disabled={busy || isEditorDirty}><ClipboardCheck size={14} /> Validate draft</button><button className="button primary" onClick={publishDraft} disabled={busy || !validation?.valid || draft.status !== "VALIDATED"}><UploadCloud size={14} /> Publish version</button></div>
              </div>
            </>
          )}
        </section>
      )}

      {canEdit && management && <div className="knowledge-footnote"><RefreshCw size={13} /> Existing reviews retain the exact Knowledge Pack snapshot and fingerprint they were analysed against. Publishing a new version affects future reviews; it does not rewrite historic decisions.</div>}
    </div>
  );
}
