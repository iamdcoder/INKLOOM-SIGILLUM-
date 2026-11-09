"use client";

import { type FormEvent, type ReactNode, useMemo, useState } from "react";
import { Plus } from "lucide-react";

type Section = "facts" | "policies" | "terminology" | "voice";
type Source = {
  source_id: string;
  name: string;
  version: number;
  status: string;
  reference_text?: string | null;
};
type Snapshot = {
  facts?: unknown[];
  policies?: unknown[];
  terminology?: Record<string, unknown> & { preferred_terms?: unknown[]; prohibited_or_review_terms?: unknown[] };
  voice?: Record<string, unknown>;
};
type Props = {
  section: Section;
  snapshot: Snapshot;
  sources: Source[];
  channels: string[];
  disabled?: boolean;
  onSave: (section: Section, content: unknown, message: string) => Promise<void>;
};

function recordId(prefix: string) {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "").slice(0, 12).toUpperCase()}`;
}

function splitCsv(value: string) {
  return value.split(",").map((part) => part.trim()).filter(Boolean);
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "Unable to save this Knowledge Pack record.";
}

function asIso(value: string) {
  return value ? new Date(value).toISOString() : null;
}

function Field({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return <label className={wide ? "wide" : ""}>{label}{children}</label>;
}

function FactForm({ snapshot, sources, channels, disabled, onSave }: Props) {
  const [formError, setFormError] = useState("");
  const [subject, setSubject] = useState("");
  const [predicate, setPredicate] = useState("");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("");
  const [qualifier, setQualifier] = useState("");
  const [denominator, setDenominator] = useState("");
  const [offerId, setOfferId] = useState("");
  const [geography, setGeography] = useState("IN");
  const [channel, setChannel] = useState(channels[0] || "");
  const [locale, setLocale] = useState("en-IN");
  const [audience, setAudience] = useState("consumer");
  const [sourceId, setSourceId] = useState("");
  const [quote, setQuote] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const availableSources = useMemo(() => sources.filter((item) => item.status === "approved" && item.reference_text?.trim()), [sources]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const source = availableSources.find((item) => item.source_id === sourceId);
    if (!source) throw new Error("Choose an approved source with retained reference text before adding a fact.");
    if (!quote.trim() || !source.reference_text?.includes(quote.trim())) throw new Error("The exact quote must occur in the selected approved source text.");
    if (validFrom && validUntil && new Date(validUntil) < new Date(validFrom)) throw new Error("Fact validity end cannot precede its start.");
    const parsedNumber = Number(value);
    const fact = {
      fact_id: recordId("FACT"), subject: subject.trim(), predicate: predicate.trim(),
      value: value.trim() !== "" && Number.isFinite(parsedNumber) ? parsedNumber : value.trim(),
      unit: unit.trim() || null, qualifier: qualifier || null, denominator: denominator.trim() || null,
      offer_id: offerId.trim() || null, geography: geography.trim() || null, channel: channel || null,
      locale: locale.trim() || null, audience: audience.trim() || null,
      source_ref: { source_id: source.source_id, source_version: source.version, quote: quote.trim() },
      valid_from: asIso(validFrom), valid_until: asIso(validUntil), recorded_at: new Date().toISOString(), status: "draft",
    };
    await onSave("facts", [...(snapshot.facts || []), fact], "Fact added to the draft. Review its source and record an explicit owner decision before publication.");
    setSubject(""); setPredicate(""); setValue(""); setUnit(""); setQualifier(""); setDenominator("");
    setOfferId(""); setSourceId(""); setQuote(""); setValidFrom(""); setValidUntil("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    setFormError("");
    try { await submit(event); } catch (reason) { setFormError(errorMessage(reason)); }
  }

  return (
    <form className="knowledge-guided-form" onSubmit={handleSubmit}>
      <div className="eyebrow">ADD FACT · SOURCE-LINKED</div>
      {formError && <p className="knowledge-form-error" role="alert">{formError}</p>}
      <p className="knowledge-guided-note">The fact starts as a draft. It cannot become authoritative without an approved source, exact quote, owner decision and pack publication.</p>
      <div className="knowledge-guided-grid">
        <Field label="Subject"><input required value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={240} placeholder="ORBITA Air One" /></Field>
        <Field label="Predicate"><input required value={predicate} onChange={(e) => setPredicate(e.target.value)} maxLength={120} placeholder="maximum_saving" /></Field>
        <Field label="Value"><input required value={value} onChange={(e) => setValue(e.target.value)} maxLength={160} placeholder="28" /></Field>
        <Field label="Unit"><input value={unit} onChange={(e) => setUnit(e.target.value)} maxLength={40} placeholder="%" /></Field>
        <Field label="Qualifier"><select value={qualifier} onChange={(e) => setQualifier(e.target.value)}><option value="">None specified</option><option value="up_to">Up to</option><option value="at_least">At least</option><option value="average">Average</option><option value="guaranteed">Guaranteed</option><option value="may">May</option></select></Field>
        <Field label="Denominator (optional)"><input value={denominator} onChange={(e) => setDenominator(e.target.value)} maxLength={160} /></Field>
        <Field label="Offer / campaign ID"><input value={offerId} onChange={(e) => setOfferId(e.target.value)} maxLength={160} /></Field>
        <Field label="Geography"><input value={geography} onChange={(e) => setGeography(e.target.value)} maxLength={80} /></Field>
        <Field label="Channel"><select value={channel} onChange={(e) => setChannel(e.target.value)}><option value="">Any channel</option>{channels.map((item) => <option key={item} value={item}>{item}</option>)}</select></Field>
        <Field label="Locale"><input value={locale} onChange={(e) => setLocale(e.target.value)} maxLength={40} /></Field>
        <Field label="Audience"><input value={audience} onChange={(e) => setAudience(e.target.value)} maxLength={100} /></Field>
        <Field label="Approved source"><select required value={sourceId} onChange={(e) => setSourceId(e.target.value)}><option value="">Select approved source</option>{availableSources.map((item) => <option key={item.source_id} value={item.source_id}>{item.name} · v{item.version}</option>)}</select></Field>
        <Field label="Valid from"><input type="datetime-local" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} /></Field>
        <Field label="Valid until"><input type="datetime-local" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} /></Field>
        <Field label="Exact supporting quote" wide><textarea required rows={3} value={quote} onChange={(e) => setQuote(e.target.value)} maxLength={20000} placeholder="Paste the exact quote from the selected approved source." /></Field>
      </div>
      {availableSources.length === 0 && <p className="text-warning">Approve a reference-text source first. Uploaded PDFs/DOCX are eligible once they are clean, fully extracted and approved.</p>}
      <button className="button secondary" type="submit" disabled={disabled || availableSources.length === 0}><Plus size={14} /> Add draft fact</button>
    </form>
  );
}

function PolicyForm({ snapshot, sources, channels, disabled, onSave }: Props) {
  const [formError, setFormError] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("claims");
  const [rule, setRule] = useState("");
  const [severity, setSeverity] = useState("review_required");
  const [action, setAction] = useState("review");
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [locale, setLocale] = useState("en-IN");
  const [geography, setGeography] = useState("IN");
  const [validFrom, setValidFrom] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [sourceQuote, setSourceQuote] = useState("");
  const availableSources = useMemo(() => sources.filter((item) => item.status === "approved" && item.reference_text?.trim()), [sources]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (validFrom && validUntil && new Date(validUntil) < new Date(validFrom)) throw new Error("Policy validity end cannot precede its start.");
    const source = availableSources.find((item) => item.source_id === sourceId);
    if (!source) throw new Error("Choose an approved source with retained text before adding a policy clause.");
    if (!sourceQuote.trim() || !source.reference_text?.includes(sourceQuote.trim())) throw new Error("The exact policy clause quote must occur in the selected approved source text.");
    const policy = {
      policy_id: recordId("POL"), name: name.trim(), category, rule: rule.trim(), severity,
      required_action: action, scope: { channel: selectedChannels, locale: locale.trim() ? [locale.trim()] : [], geography: geography.trim() ? [geography.trim()] : [] },
      source_ref: { source_id: source.source_id, source_version: source.version, quote: sourceQuote.trim() },
      valid_from: asIso(validFrom), valid_until: asIso(validUntil), status: "draft",
    };
    await onSave("policies", [...(snapshot.policies || []), policy], "Policy clause added to the draft. Record an owner decision before publishing.");
    setName(""); setRule(""); setSelectedChannels([]); setValidFrom(""); setValidUntil(""); setSourceId(""); setSourceQuote("");
  }
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    setFormError("");
    try { await submit(event); } catch (reason) { setFormError(errorMessage(reason)); }
  }
  return (
    <form className="knowledge-guided-form" onSubmit={handleSubmit}>
      <div className="eyebrow">ADD POLICY CLAUSE · SOURCE-LINKED</div>
      {formError && <p className="knowledge-form-error" role="alert">{formError}</p>}
      <p className="knowledge-guided-note">New policy clauses must retain their exact approved source/version and a verbatim clause excerpt. The owner decision is recorded separately.</p>
      <div className="knowledge-guided-grid">
        <Field label="Policy name"><input required value={name} onChange={(e) => setName(e.target.value)} maxLength={240} /></Field>
        <Field label="Category"><select value={category} onChange={(e) => setCategory(e.target.value)}><option value="claims">Claims</option><option value="terminology">Terminology</option><option value="accessibility">Accessibility</option><option value="visual_identity">Visual identity</option><option value="legal">Legal / disclaimer</option><option value="tone">Tone</option><option value="other">Other</option></select></Field>
        <Field label="Severity"><select value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="blocking">Blocking</option><option value="review_required">Review required</option><option value="suggestion">Suggestion</option><option value="informational">Informational</option></select></Field>
        <Field label="Required action"><select value={action} onChange={(e) => setAction(e.target.value)}><option value="review">Review</option><option value="correct">Correct</option><option value="remove">Remove</option><option value="disclose">Add disclosure</option><option value="manual_check">Manual check</option></select></Field>
        <Field label="Applicable channels" wide><div className="knowledge-checkbox-row">{channels.map((item) => <label key={item}><input type="checkbox" checked={selectedChannels.includes(item)} onChange={(e) => setSelectedChannels((current) => e.target.checked ? [...current, item] : current.filter((x) => x !== item))} />{item}</label>)}</div></Field>
        <Field label="Locale"><input value={locale} onChange={(e) => setLocale(e.target.value)} maxLength={40} /></Field>
        <Field label="Geography"><input value={geography} onChange={(e) => setGeography(e.target.value)} maxLength={80} /></Field>
        <Field label="Valid from"><input type="datetime-local" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} /></Field>
        <Field label="Valid until"><input type="datetime-local" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} /></Field>
        <Field label="Rule / policy text" wide><textarea required rows={3} value={rule} onChange={(e) => setRule(e.target.value)} maxLength={4000} /></Field>
        <Field label="Approved source"><select required value={sourceId} onChange={(e) => setSourceId(e.target.value)}><option value="">Select approved source</option>{availableSources.map((item) => <option key={item.source_id} value={item.source_id}>{item.name} · v{item.version}</option>)}</select></Field>
        <Field label="Exact source clause" wide><textarea required rows={2} value={sourceQuote} onChange={(e) => setSourceQuote(e.target.value)} maxLength={12000} placeholder="Paste the exact clause from the selected source." /></Field>
      </div>
      {availableSources.length === 0 && <p className="text-warning">Approve a source with retained reference text before adding a new policy clause.</p>}
      <button className="button secondary" type="submit" disabled={disabled || availableSources.length === 0}><Plus size={14} /> Add draft policy</button>
    </form>
  );
}

function TermForm({ snapshot, disabled, onSave }: Props) {
  const [formError, setFormError] = useState("");
  const [kind, setKind] = useState("preferred");
  const [text, setText] = useState("");
  const [locale, setLocale] = useState("en-IN");
  const [scope, setScope] = useState("all");
  const [reason, setReason] = useState("");
  const [severity, setSeverity] = useState("review_required");
  const [preferredId, setPreferredId] = useState("");
  const terminology = snapshot.terminology || {};
  const preferredRows = Array.isArray(terminology.preferred_terms) ? terminology.preferred_terms as Array<Record<string, unknown>> : [];
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const record = kind === "preferred"
      ? { term_id: recordId("TERM"), preferred: text.trim(), locale: locale.trim(), scope: splitCsv(scope), status: "draft" }
      : { term_id: recordId("TERM"), variant: text.trim(), preferred_term_id: preferredId || null, locale: locale.trim(), scope: splitCsv(scope), reason: reason.trim(), severity, status: "draft" };
    const next = {
      ...terminology,
      preferred_terms: kind === "preferred" ? [...(terminology.preferred_terms || []), record] : (terminology.preferred_terms || []),
      prohibited_or_review_terms: kind === "prohibited" ? [...(terminology.prohibited_or_review_terms || []), record] : (terminology.prohibited_or_review_terms || []),
    };
    await onSave("terminology", next, "Terminology entry added to the draft. Explicit owner approval and publication are still required.");
    setText(""); setReason(""); setPreferredId("");
  }
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    setFormError("");
    try { await submit(event); } catch (reason) { setFormError(errorMessage(reason)); }
  }
  return (
    <form className="knowledge-guided-form" onSubmit={handleSubmit}>
      <div className="eyebrow">ADD TERMINOLOGY ENTRY</div>
      {formError && <p className="knowledge-form-error" role="alert">{formError}</p>}
      <div className="knowledge-guided-grid">
        <Field label="Entry type"><select value={kind} onChange={(e) => setKind(e.target.value)}><option value="preferred">Preferred / canonical term</option><option value="prohibited">Prohibited / review variant</option></select></Field>
        <Field label={kind === "preferred" ? "Preferred term" : "Prohibited or review variant"}><input required value={text} onChange={(e) => setText(e.target.value)} maxLength={240} /></Field>
        <Field label="Locale"><input value={locale} onChange={(e) => setLocale(e.target.value)} maxLength={40} /></Field>
        <Field label="Scope tags (comma-separated)"><input value={scope} onChange={(e) => setScope(e.target.value)} maxLength={500} placeholder="all, product-id, campaign-id" /></Field>
        {kind === "prohibited" && <>
          <Field label="Preferred term link"><select value={preferredId} onChange={(e) => setPreferredId(e.target.value)}><option value="">No preferred term</option>{preferredRows.map((item, index) => <option key={String(item.term_id || index)} value={String(item.term_id || "")}>{String(item.preferred || item.term_id)}</option>)}</select></Field>
          <Field label="Severity"><select value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="blocking">Blocking</option><option value="review_required">Review required</option><option value="suggestion">Suggestion</option><option value="informational">Informational</option></select></Field>
          <Field label="Reason" wide><textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} required maxLength={1000} /></Field>
        </>}
      </div>
      <button className="button secondary" type="submit" disabled={disabled}><Plus size={14} /> Add draft term</button>
    </form>
  );
}

function VoiceForm({ snapshot, disabled, onSave }: Props) {
  const [formError, setFormError] = useState("");
  const [kind, setKind] = useState("trait");
  const [text, setText] = useState("");
  const [labels, setLabels] = useState("");
  const [reason, setReason] = useState("");
  const [severity, setSeverity] = useState("review_required");
  const [locale, setLocale] = useState("en-IN");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const voice = snapshot.voice || {};
    const next = { ...voice } as Record<string, unknown>;
    if (kind === "trait") next.voice_traits = [...(Array.isArray(voice.voice_traits) ? voice.voice_traits : []), text.trim()];
    if (kind === "example") next.approved_examples = [...(Array.isArray(voice.approved_examples) ? voice.approved_examples : []), { example_id: recordId("VOICE"), text: text.trim(), labels: splitCsv(labels), locale: locale.trim() }];
    if (kind === "pattern") next.disallowed_patterns = [...(Array.isArray(voice.disallowed_patterns) ? voice.disallowed_patterns : []), { pattern_id: recordId("VOICE"), pattern: text.trim(), reason: reason.trim(), severity, locale: locale.trim() }];
    await onSave("voice", next, "Voice guidance added to the unpublished draft. It becomes active only after pack publication.");
    setText(""); setLabels(""); setReason("");
  }
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    setFormError("");
    try { await submit(event); } catch (reason) { setFormError(errorMessage(reason)); }
  }
  return (
    <form className="knowledge-guided-form" onSubmit={handleSubmit}>
      <div className="eyebrow">ADD VOICE GUIDANCE</div>
      {formError && <p className="knowledge-form-error" role="alert">{formError}</p>}
      <div className="knowledge-guided-grid">
        <Field label="Guidance type"><select value={kind} onChange={(e) => setKind(e.target.value)}><option value="trait">Voice trait</option><option value="example">Approved voice example</option><option value="pattern">Disallowed / review pattern</option></select></Field>
        <Field label={kind === "trait" ? "Trait" : kind === "example" ? "Approved example" : "Disallowed phrase"}><input required value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} /></Field>
        {kind !== "trait" && <Field label="Locale"><input value={locale} onChange={(e) => setLocale(e.target.value)} maxLength={40} /></Field>}
        {kind === "example" && <Field label="Labels (comma-separated)"><input value={labels} onChange={(e) => setLabels(e.target.value)} maxLength={500} /></Field>}
        {kind === "pattern" && <>
          <Field label="Severity"><select value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="blocking">Blocking</option><option value="review_required">Review required</option><option value="suggestion">Suggestion</option><option value="informational">Informational</option></select></Field>
          <Field label="Reason" wide><textarea required rows={2} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} /></Field>
        </>}
      </div>
      <button className="button secondary" type="submit" disabled={disabled}><Plus size={14} /> Add voice guidance</button>
    </form>
  );
}

export default function KnowledgeRecordForms(props: Props) {
  if (props.section === "facts") return <FactForm {...props} />;
  if (props.section === "policies") return <PolicyForm {...props} />;
  if (props.section === "terminology") return <TermForm {...props} />;
  if (props.section === "voice") return <VoiceForm {...props} />;
  return null;
}
