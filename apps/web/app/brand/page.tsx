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
  getSessionUserRaw,
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

type PackSnapshot = {
  brand: Record<string, unknown>;
  facts: unknown[];
  policies: unknown[];
  terminology: Record<string, unknown>;
  voice: Record<string, unknown>;
  assets: Record<string, unknown>;
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
  { key: "assets", label: "Approved assets", description: "Asset manifest, approval status and usage metadata." },
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

  async function refreshManagement() {
    const [current, detail] = await Promise.all([
      api<PackSummary>("/brands/current"),
      api<ManagementPayload>("/brands/current/management"),
    ]);
    setSummary(current);
    setManagement(detail);
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
          if (!cancelled) setManagement(result);
        })
        .catch((reason: unknown) => {
          if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load Knowledge Pack management details.");
        });
    }
    return () => {
      cancelled = true;
    };
  }, [canViewManagement]);

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
