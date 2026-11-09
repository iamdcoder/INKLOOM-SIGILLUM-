"use client";

import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent, MutableRefObject } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileUp,
  FileWarning,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";
import { API_BASE, api, getToken, getUser } from "@/lib/api";

type Draft = {
  id: string;
  title: string;
  channel: string;
  locale: string;
  geography: string;
  audience: string;
  offer_id: string | null;
  intended_use: string;
  product_scope: string | null;
  campaign_scope: string | null;
  context_note: string | null;
  publication_at: string;
  status: string;
};

type DuplicateMatch = {
  submission_id: string;
  title: string;
  version_id: string;
  version_number: number;
  filename: string;
  created_at: string;
};

type UploadResult = {
  submission: { id: string; title: string; status: string };
  content_version: { id: string; version_number: number; sha256: string };
};

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"];

function defaultPublicationTime() {
  const value = new Date(Date.now() + 24 * 60 * 60 * 1000);
  value.setMinutes(0, 0, 0);
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function toLocalDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return defaultPublicationTime();
  return new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function formatBytes(value: number) {
  return value < 1024 * 1024 ? `${(value / 1024).toFixed(1)} KB` : `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

async function sha256File(file: File) {
  const bytes = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function uploadWithProgress(
  draftId: string,
  file: File,
  idempotencyKey: string,
  onProgress: (value: number) => void,
  signalRef: MutableRefObject<XMLHttpRequest | null>,
) {
  return new Promise<UploadResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    signalRef.current = xhr;
    xhr.open("POST", `${API_BASE}/submissions/${draftId}/content`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Idempotency-Key", idempotencyKey);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    };
    xhr.onload = () => {
      signalRef.current = null;
      let payload: { detail?: string | { message?: string }; [key: string]: unknown } = {};
      try {
        payload = JSON.parse(xhr.responseText || "{}") as typeof payload;
      } catch {
        reject(new Error("The server returned an unreadable upload response."));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
        resolve(payload as UploadResult);
        return;
      }
      const detail = payload.detail;
      reject(new Error(typeof detail === "string" ? detail : detail?.message || `Upload failed (${xhr.status}).`));
    };
    xhr.onerror = () => {
      signalRef.current = null;
      reject(new Error("Network error during upload. Your draft remains saved; retry with the same file."));
    };
    xhr.onabort = () => {
      signalRef.current = null;
      reject(new Error("Upload cancelled. Your draft has been kept so you can retry."));
    };
    const body = new FormData();
    body.append("file", file);
    xhr.send(body);
  });
}

export default function NewSubmissionPage() {
  const router = useRouter();
  const uploadRef = useRef<XMLHttpRequest | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [draftId, setDraftId] = useState("");
  const [brandName, setBrandName] = useState("Selected brand workspace");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [channel, setChannel] = useState("direct_web");
  const [locale, setLocale] = useState("en-IN");
  const [geography, setGeography] = useState("IN");
  const [audience, setAudience] = useState("consumer");
  const [intendedUse, setIntendedUse] = useState("general");
  const [offer, setOffer] = useState("OFFER-ORBITA-OCT-NOV-2026");
  const [productScope, setProductScope] = useState("");
  const [campaignScope, setCampaignScope] = useState("");
  const [contextNote, setContextNote] = useState("");
  const [date, setDate] = useState(defaultPublicationTime);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [duplicateMatches, setDuplicateMatches] = useState<DuplicateMatch[]>([]);
  const [duplicateConfirmed, setDuplicateConfirmed] = useState(false);

  useEffect(() => {
    const user = getUser();
    if (user?.brand_name) setBrandName(user.brand_name);
    const requestedDraft = new URLSearchParams(window.location.search).get("draft");
    if (!requestedDraft) return;
    setDraftId(requestedDraft);
    api<Draft>(`/submissions/${requestedDraft}`)
      .then((draft) => {
        if (draft.status !== "DRAFT") {
          router.replace(`/reviews/${draft.id}`);
          return;
        }
        setTitle(draft.title || "");
        setChannel(draft.channel || "direct_web");
        setLocale(draft.locale || "en-IN");
        setGeography(draft.geography || "IN");
        setAudience(draft.audience || "consumer");
        setIntendedUse(draft.intended_use || "general");
        setOffer(draft.offer_id || "");
        setProductScope(draft.product_scope || "");
        setCampaignScope(draft.campaign_scope || "");
        setContextNote(draft.context_note || "");
        setDate(toLocalDateTime(draft.publication_at));
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Draft could not be loaded."));
  }, [router]);

  function chooseFile(candidate: File | null) {
    setError("");
    setNotice("");
    setDuplicateMatches([]);
    setDuplicateConfirmed(false);
    if (!candidate) {
      setFile(null);
      return;
    }
    const lowerName = candidate.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension))) {
      setError("Unsupported file. Choose PDF, DOCX, TXT, PNG or JPG.");
      return;
    }
    if (candidate.size <= 0) {
      setError("The selected file is empty.");
      return;
    }
    if (candidate.size > MAX_UPLOAD_BYTES) {
      setError(`The selected file is larger than ${formatBytes(MAX_UPLOAD_BYTES)}.`);
      return;
    }
    setFile(candidate);
    if (!title.trim()) setTitle(candidate.name.replace(/\.[^.]+$/, ""));
  }

  function payload() {
    return {
      title: title.trim() || file?.name || "Untitled submission",
      channel,
      locale,
      geography,
      audience,
      offer_id: offer || null,
      intended_use: intendedUse,
      product_scope: productScope.trim() || null,
      campaign_scope: campaignScope.trim() || null,
      context_note: contextNote.trim() || null,
      publication_at: new Date(date).toISOString(),
    };
  }

  async function saveDraft() {
    setError("");
    setNotice("");
    const draft = draftId
      ? await api<Draft>(`/submissions/${draftId}/draft`, { method: "PATCH", body: JSON.stringify(payload()) })
      : await api<Draft>("/submissions/drafts", { method: "POST", body: JSON.stringify(payload()) });
    setDraftId(draft.id);
    router.replace(`/submissions/new?draft=${draft.id}`, { scroll: false });
    setNotice("Draft saved. You can return to it from your submissions list.");
    return draft;
  }

  async function onSaveDraft() {
    try {
      await saveDraft();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Draft could not be saved.");
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose a file to review.");
      return;
    }
    if (!getToken()) {
      setError("Your session has expired. Sign in again before uploading.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    setProgress(0);
    try {
      const savedDraft = await saveDraft();
      const digest = await sha256File(file);
      if (!duplicateConfirmed) {
        const duplicateCheck = await api<{ duplicate: boolean; matches: DuplicateMatch[] }>("/submissions/duplicate-check", {
          method: "POST",
          body: JSON.stringify({ sha256: digest }),
        });
        if (duplicateCheck.duplicate) {
          setDuplicateMatches(duplicateCheck.matches);
          setBusy(false);
          return;
        }
      }
      const idempotencyStorageKey = `sigillum_upload_key:${savedDraft.id}:${digest}`;
      let idempotencyKey = sessionStorage.getItem(idempotencyStorageKey);
      if (!idempotencyKey) {
        idempotencyKey = crypto.randomUUID();
        sessionStorage.setItem(idempotencyStorageKey, idempotencyKey);
      }
      const result = await uploadWithProgress(savedDraft.id, file, idempotencyKey, setProgress, uploadRef);
      sessionStorage.removeItem(idempotencyStorageKey);
      router.push(`/reviews/${result.submission.id}`);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed. Your draft remains available.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelDraft() {
    uploadRef.current?.abort();
    if (!draftId) {
      router.push("/submissions");
      return;
    }
    try {
      await api(`/submissions/${draftId}`, { method: "DELETE" });
      router.push("/submissions");
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Draft could not be cancelled.");
    }
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0] || null);
  }

  return (
    <div className="page-stack narrow-page">
      <Link href="/submissions" className="back-link"><ArrowLeft size={15} /> Back to submissions</Link>
      <section>
        <div className="eyebrow">NEW ASSURANCE REVIEW · SECURE INTAKE</div>
        <h1>Submit content.</h1>
        <p className="subhead">Save the publication context first. Your original file becomes an immutable, scanned version when uploaded.</p>
      </section>

      <form onSubmit={submit} className="panel form-panel">
        <div className="form-section-heading">
          <span className="step-number">01</span>
          <div><h2>Content asset</h2><p>Choose the exact asset intended for publication.</p></div>
        </div>
        <label
          className={`dropzone secure-dropzone ${dragging ? "is-dragging" : ""} ${file ? "has-file" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          {file ? <>
            <div className="upload-file-icon"><FileUp size={24} /></div>
            <b>{file.name}</b>
            <small>{formatBytes(file.size)} · Ready for SHA-256 duplicate check</small>
          </> : <>
            <div className="upload-file-icon"><UploadCloud size={25} /></div>
            <b>Drop your file here or browse</b>
            <small>PDF, DOCX, TXT, PNG or JPG · Maximum 10 MB</small>
          </>}
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" onChange={(event) => chooseFile(event.target.files?.[0] || null)} />
        </label>
        {file && <button type="button" className="button secondary file-clear-action" onClick={() => { chooseFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}><X size={14} /> Remove selected file</button>}
        <div className="secure-intake-note"><LockKeyhole size={14} /><span>Server-side signature, structure, size and malware checks run before the original is stored or analysed.</span></div>

        <label>Submission title<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. November campaign launch flyer" maxLength={240} /></label>

        <div className="form-section-heading separated">
          <span className="step-number">02</span>
          <div><h2>Publication context</h2><p>Scope, locale and intended publication time are bound to this review.</p></div>
        </div>
        <div className="form-grid">
          <label>Channel<select value={channel} onChange={(event) => { setChannel(event.target.value); if (event.target.value === "social") setOffer(""); }}><option value="direct_web">Direct web</option><option value="social">Social</option><option value="print">Print</option></select></label>
          <label>Intended use<select value={intendedUse} onChange={(event) => setIntendedUse(event.target.value)}><option value="general">General content</option><option value="brand_lockup">Brand lockup / logo placement</option><option value="campaign">Campaign creative</option><option value="product_detail">Product detail</option><option value="social_ad">Social advertisement</option><option value="email_banner">Email banner</option><option value="website_hero">Website hero</option><option value="packaging">Packaging</option></select></label>
          <label>Locale<input value={locale} onChange={(event) => setLocale(event.target.value)} maxLength={20} required /></label>
          <label>Geography<input value={geography} onChange={(event) => setGeography(event.target.value)} maxLength={20} required /></label>
          <label>Audience<input value={audience} onChange={(event) => setAudience(event.target.value)} maxLength={80} required /></label>
          <label>Offer scope<select value={offer} onChange={(event) => setOffer(event.target.value)}><option value="OFFER-ORBITA-OCT-NOV-2026">Oct–Nov 2026 · Direct web</option><option value="OFFER-ORBITA-JUL-SEP-2026">Jul–Sep 2026 · Expired</option><option value="OFFER-ORBITA-DEC-2026">Dec 2026 · Future</option><option value="OFFER-ORBITA-CONFLICT-TEST">Conflict test · Social</option><option value="">No offer selected</option></select></label>
          <label>Product scope<input value={productScope} onChange={(event) => setProductScope(event.target.value)} placeholder="e.g. ORBITA Air One" maxLength={160} /></label>
          <label>Campaign scope<input value={campaignScope} onChange={(event) => setCampaignScope(event.target.value)} placeholder="e.g. Winter launch" maxLength={160} /></label>
          <label className="span-two">Intended publication time<input type="datetime-local" value={date} onChange={(event) => setDate(event.target.value)} required /></label>
          <label className="span-two">Additional context<textarea value={contextNote} onChange={(event) => setContextNote(event.target.value)} placeholder="Optional context that helps scope this review." rows={3} maxLength={2000} /></label>
        </div>
        <div className="context-note"><ShieldCheck size={16} /><span><b>Workspace: {brandName}</b><small>Originals are private, hash-verified and preserved as immutable versions.</small></span></div>

        {duplicateMatches.length > 0 && <div className="duplicate-warning">
          <div className="duplicate-warning-title"><FileWarning size={17} /><b>This file already exists in this workspace.</b></div>
          <p>Matching SHA-256 content was found in the following version(s). Uploading again will create a new submission.</p>
          {duplicateMatches.map((match) => <div className="duplicate-match" key={match.version_id}><span><b>{match.title}</b><small>{match.filename} · v{match.version_number}</small></span><span>{new Date(match.created_at).toLocaleDateString()}</span></div>)}
          <label className="confirm-duplicate"><input type="checkbox" checked={duplicateConfirmed} onChange={(event) => setDuplicateConfirmed(event.target.checked)} /> I reviewed the matches and still want to submit this file.</label>
        </div>}

        {busy && <div className="upload-progress-panel">
          <div className="progress-label"><span>{progress >= 100 ? "File received · analysing" : "Uploading original"}</span><b>{progress}%</b></div>
          <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
          <small>Keep this page open until the review is created. Your draft is already saved.</small>
        </div>}
        {notice && <div className="alert success"><CheckCircle2 size={15} /> {notice}</div>}
        {error && <div className="alert error">{error}</div>}

        <div className="form-actions secure-form-actions">
          <span className="privacy-note"><LockKeyhole size={14} /> No file is stored until scanner approval.</span>
          <div className="secure-action-buttons">
            {busy && <button type="button" className="button secondary" onClick={() => uploadRef.current?.abort()}><X size={14} /> Cancel upload</button>}
            <button type="button" className="button secondary" disabled={busy} onClick={onSaveDraft}><RefreshCw size={14} /> Save draft</button>
            <button type="button" className="button danger" disabled={busy} onClick={cancelDraft}>Discard draft</button>
            <button className="button primary" disabled={busy || !file || (duplicateMatches.length > 0 && !duplicateConfirmed)}>{busy ? "Processing…" : "Run assurance review"}<ArrowRight size={15} /></button>
          </div>
        </div>
      </form>
      <div className="disclaimer">SIGILLUM ANALYSES AND EXPLAINS. IT DOES NOT PUBLISH CONTENT OR REPLACE AUTHORISED REVIEWERS.</div>
    </div>
  );
}
