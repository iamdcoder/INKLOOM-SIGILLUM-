"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import Image from "next/image";
import { useCallback,useEffect,useMemo,useState,useSyncExternalStore } from "react";
import { AlertTriangle,ArrowLeft,ArrowRight,Check,CheckCircle2,ChevronDown,Copy,Crosshair,FileText,History,Info,LockKeyhole,RefreshCw,Search,ShieldAlert,SlidersHorizontal,Sparkles,X } from "lucide-react";
import { API_BASE,api,Finding,ReviewPayload,VersionHistoryItem,getToken,getSessionUserRaw,parseSessionUser,subscribeToSession } from "@/lib/api";
const EMPTY_FINDINGS: Finding[] = [];

export default function ReviewPage(){const params=useParams<{id:string}>();const router=useRouter();const sessionSnapshot=useSyncExternalStore(subscribeToSession,getSessionUserRaw,()=>null);const sessionUser=useMemo(()=>parseSessionUser(sessionSnapshot),[sessionSnapshot]);const role=sessionUser?.role||"";const [data,setData]=useState<ReviewPayload|null>(null);const [history,setHistory]=useState<VersionHistoryItem[]>([]);const [error,setError]=useState("");const [busy,setBusy]=useState(false);const [reason,setReason]=useState("");const [decisionMessage,setDecisionMessage]=useState("");const [expanded,setExpanded]=useState<string|null>(null);const [activeFindingId,setActiveFindingId]=useState<string|null>(null);const [activeRegionId,setActiveRegionId]=useState<string|null>(null);const [findingQuery,setFindingQuery]=useState("");const [severityFilter,setSeverityFilter]=useState("all");const [categoryFilter,setCategoryFilter]=useState("all");const [verdictFilter,setVerdictFilter]=useState("all");const [statusFilter,setStatusFilter]=useState("all");const [sortOrder,setSortOrder]=useState("risk");const [replacement,setReplacement]=useState<Record<string,string>>({});const [revisionFile,setRevisionFile]=useState<File|null>(null);const [revisionSummary,setRevisionSummary]=useState("");const [revisionBusy,setRevisionBusy]=useState(false);const [previewResource,setPreviewResource]=useState<{versionId:string;url:string}|null>(null);const [previewFailure,setPreviewFailure]=useState<{versionId:string;message:string}|null>(null);
 const fetchReview=useCallback(async()=>{const result=await api<ReviewPayload>(`/reviews/${params.id}`);let versions:VersionHistoryItem[]=[];try{const timeline=await api<{versions:VersionHistoryItem[]}>(`/submissions/${result.submission.id}/history`);versions=timeline.versions;}catch{versions=[];}return {result,versions};},[params.id]);
 const load=useCallback(async()=>{setError("");try{const {result,versions}=await fetchReview();setData(result);setHistory(versions);}catch(e){setError(e instanceof Error?e.message:"Unable to load review");}},[fetchReview]);
 useEffect(()=>{let cancelled=false;fetchReview().then(({result,versions})=>{if(cancelled)return;setData(result);setHistory(versions);}).catch(e=>{if(cancelled)return;setError(e instanceof Error?e.message:"Unable to load review");});return()=>{cancelled=true;};},[fetchReview]);
 useEffect(()=>{
  const versionId=data?.content_version?.id;
  if(!versionId)return;
  let cancelled=false;
  let objectUrl="";
  const controller=new AbortController();
  const headers=new Headers();
  const token=getToken();
  if(token)headers.set("Authorization",`Bearer ${token}`);

  fetch(`${API_BASE}/content-versions/${versionId}/download`,{headers,signal:controller.signal})
   .then(async response=>{
    if(!response.ok)throw new Error("Original asset preview is unavailable.");
    return response.blob();
   })
   .then(blob=>{
    if(cancelled)return;
    objectUrl=URL.createObjectURL(blob);
    setPreviewResource({versionId,url:objectUrl});
   })
   .catch(error=>{
    if(!cancelled && !(error instanceof DOMException && error.name==="AbortError")){
     setPreviewFailure({versionId,message:error instanceof Error?error.message:"Preview unavailable"});
    }
   });

  return ()=>{
   cancelled=true;
   controller.abort();
   if(objectUrl)URL.revokeObjectURL(objectUrl);
  };
 },[data?.content_version?.id]);
 const activeVersionId=data?.content_version?.id;
 const previewUrl=previewResource && previewResource.versionId===activeVersionId?previewResource.url:"";
 const previewError=previewFailure && previewFailure.versionId===activeVersionId?previewFailure.message:"";
 const findings=data?.findings??EMPTY_FINDINGS;const blockers=findings.filter(f=>["blocking","review_required"].includes(f.severity)&&!(["SUPPORTED","INFORMATIONAL"].includes(f.verdict))&&f.status!=="RESOLVED");const canDecide=["reviewer","brand_owner","administrator"].includes(role);
 const totals=useMemo(()=>({blocking:findings.filter(f=>f.severity==="blocking"&&f.status!=="RESOLVED").length,review:findings.filter(f=>f.severity==="review_required"&&f.status!=="RESOLVED").length,clear:findings.filter(f=>["SUPPORTED","INFORMATIONAL"].includes(f.verdict)).length}),[findings]);
 const categories=useMemo(()=>Array.from(new Set(findings.map(f=>f.category))).sort((a,b)=>a.localeCompare(b)),[findings]);
 const visibleFindings=useMemo(()=>{
  const query=findingQuery.trim().toLocaleLowerCase();
  const severityRank:Record<string,number>={blocking:0,review_required:1,suggestion:2,informational:3};
  return findings.filter(f=>{
   const searchable=[f.title,f.explanation,f.category,f.verdict,f.reason_code,f.content_quote||""].join(" ").toLocaleLowerCase();
   if(query&&!searchable.includes(query))return false;
   if(severityFilter!=="all"&&f.severity!==severityFilter)return false;
   if(categoryFilter!=="all"&&f.category!==categoryFilter)return false;
   if(verdictFilter!=="all"&&f.verdict!==verdictFilter)return false;
   if(statusFilter==="open"&&f.status==="RESOLVED")return false;
   if(statusFilter==="resolved"&&f.status!=="RESOLVED")return false;
   return true;
  }).sort((a,b)=>{
   if(sortOrder==="confidence-desc")return b.confidence-a.confidence;
   if(sortOrder==="confidence-asc")return a.confidence-b.confidence;
   if(sortOrder==="category")return a.category.localeCompare(b.category)||a.title.localeCompare(b.title);
   const severity=(severityRank[a.severity]??4)-(severityRank[b.severity]??4);
   if(severity!==0)return severity;
   const resolved=(a.status==="RESOLVED"?1:0)-(b.status==="RESOLVED"?1:0);
   return resolved||b.confidence-a.confidence;
  });
 },[findings,findingQuery,severityFilter,categoryFilter,verdictFilter,statusFilter,sortOrder]);
 function locateFinding(f:Finding){
  setExpanded(f.id);setActiveFindingId(f.id);
  const regionId=typeof f.region?.region_id==="string"?f.region.region_id:"";
  const isImageRegion=f.region?.kind==="ocr_line"&&Boolean(data?.content_version.mime_type.startsWith("image/"));
  if(regionId&&isImageRegion){setActiveRegionId(regionId);window.requestAnimationFrame(()=>document.getElementById("visual-region-inspector")?.scrollIntoView({behavior:"smooth",block:"center"}));return;}
  if(f.content_start!==null&&f.content_end!==null){window.requestAnimationFrame(()=>document.getElementById(`finding-span-${f.id}`)?.scrollIntoView({behavior:"smooth",block:"center"}));return;}
  setDecisionMessage("This finding has no exact text offset or extracted visual region. Inspect the original asset manually.");
 }
 function selectVisualRegion(region:Record<string,unknown>){
  const regionId=typeof region.region_id==="string"?region.region_id:"";
  setActiveRegionId(regionId||null);
  const related=findings.find(item=>item.region?.region_id===regionId);
  if(related){setExpanded(related.id);setActiveFindingId(related.id);window.requestAnimationFrame(()=>document.getElementById(`finding-card-${related.id}`)?.scrollIntoView({behavior:"smooth",block:"center"}));}
 }
 function clearFindingFilters(){setFindingQuery("");setSeverityFilter("all");setCategoryFilter("all");setVerdictFilter("all");setStatusFilter("all");setSortOrder("risk");}
 const hasActiveFilters=findingQuery.trim()!==""||severityFilter!=="all"||categoryFilter!=="all"||verdictFilter!=="all"||statusFilter!=="all";
 async function makeDecision(action:string){if((action==="REQUEST_CHANGES"||action==="REJECT"||action==="OVERRIDE")&&reason.trim().length<4){setError("Add a reason before recording this decision.");return;}setBusy(true);setError("");try{const result=await api<{submission_status:string}>(`/reviews/${data!.review.id}/decisions`,{method:"POST",body:JSON.stringify({action,reason:reason||null})});setDecisionMessage(`Decision recorded: ${result.submission_status.replaceAll("_"," ")}`);await load();}catch(e){setError(e instanceof Error?e.message:"Decision failed");}finally{setBusy(false)}}
 async function resolveFinding(f:Finding){const note=window.prompt("Explain how this finding was reviewed and resolved:","Reviewed against the approved source and accepted the correction.");if(!note)return;setBusy(true);try{await api(`/reviews/${data!.review.id}/findings/${f.id}/resolve`,{method:"POST",body:(()=>{const form=new FormData();form.append("reason",note);return form;})()});await load();}catch(e){setError(e instanceof Error?e.message:"Unable to resolve finding");}finally{setBusy(false)}}
 async function applyPatch(f:Finding){const value=replacement[f.id]||f.suggestions?.[0];if(!value||f.content_start===null||f.content_end===null)return;setBusy(true);setError("");try{const patch=await api<{id:string}>(`/reviews/${data!.review.id}/patches`,{method:"POST",body:JSON.stringify({finding_id:f.id,replacement:value,rationale:"Replace the unsupported wording with the exact approved value from the Brand Knowledge Pack."})});const next=await api<ReviewPayload>(`/patches/${patch.id}/accept`,{method:"POST"});setData(next);const timeline=await api<{versions:VersionHistoryItem[]}>(`/submissions/${next.submission.id}/history`);setHistory(timeline.versions);setDecisionMessage("A new immutable content version was created and re-verified.");}catch(e){setError(e instanceof Error?e.message:"Patch failed");}finally{setBusy(false)}}
 async function uploadRevision(){if(!revisionFile||!data)return;setRevisionBusy(true);setError("");try{const form=new FormData();form.append("file",revisionFile);form.append("change_summary",revisionSummary);const response=await fetch(`${API_BASE}/submissions/${data.submission.id}/revisions/upload`,{method:"POST",headers:{Authorization:`Bearer ${getToken()}`},body:form});const result=await response.json();if(!response.ok)throw new Error(result?.detail?.message||"Revision upload failed");setData(result);const timeline=await api<{versions:VersionHistoryItem[]}>(`/submissions/${result.submission.id}/history`);setHistory(timeline.versions);setRevisionFile(null);setRevisionSummary("");setDecisionMessage(`Version ${result.content_version.version_number} created and re-verified.`);}catch(e){setError(e instanceof Error?e.message:"Revision upload failed");}finally{setRevisionBusy(false)}}
 if(!data&&!error)return <div className="loading-panel"><div className="spinner"/>Loading evidence record…</div>;
 if(error&&!data)return <div className="page-stack"><div className="alert error">{error}</div><Link href="/submissions" className="back-link"><ArrowLeft size={15}/> Submissions</Link></div>;
 if(!data)return null;
 return <div className="page-stack"><Link href="/submissions" className="back-link"><ArrowLeft size={15}/> Back to submissions</Link><section className="review-title-row"><div><div className="eyebrow">REVIEW RECORD <span className="eyebrow-dot"/> {data.review.id.slice(0,8).toUpperCase()}</div><h1>{data.submission.title}</h1><p className="subhead">{data.content_version.filename} · Version {data.content_version.version_number} · {data.submission.channel.replaceAll("_"," ")}</p></div><div className="title-status"><span className={`status-pill ${data.submission.status==="APPROVED"?"success":"warning"}`}><i/>{data.submission.status.replaceAll("_"," ")}</span><button className="button secondary" onClick={load}><RefreshCw size={15}/> Refresh</button></div></section>
 {decisionMessage&&<div className="alert success"><CheckCircle2 size={17}/>{decisionMessage}</div>}{error&&<div className="alert error">{error}</div>}
 <section className="review-summary-grid"><div className="summary-tile"><span>BLOCKING</span><b className="text-red">{totals.blocking}</b><small>Needs resolution</small></div><div className="summary-tile"><span>REVIEW REQUIRED</span><b className="text-amber">{totals.review}</b><small>Human inspection</small></div><div className="summary-tile"><span>SUPPORTED / INFO</span><b className="text-green">{totals.clear}</b><small>Evidence or rule match</small></div><div className="summary-tile"><span>EXTRACTION</span><b>{Math.round(data.content_version.extraction_confidence*100)}%</b><small>{data.content_version.extraction_status}</small></div></section>
 {data.content_version.warnings.map(w=><div className="alert warning" key={w}><AlertTriangle size={17}/>{w}</div>)}
 <div className="workbench-grid"><section className="panel ledger-panel"><div className="panel-heading"><div><div className="eyebrow">CANONICAL FINDING LEDGER</div><h2>{visibleFindings.length} of {findings.length} findings</h2></div><span className="channel-tag">{data.review.brand_pack_version}</span></div>{findings.length===0?<div className="empty-state"><CheckCircle2 size={29}/><h3>No findings raised</h3><p>No configured check raised an issue. This is not a guarantee of complete compliance.</p></div>:<><div className="finding-toolbar"><label className="finding-search"><Search size={15}/><span className="visually-hidden">Search findings</span><input type="search" value={findingQuery} onChange={event=>setFindingQuery(event.target.value)} placeholder="Search issues, quotes or reason codes…"/></label><div className="finding-filter-grid"><label><span>Severity</span><select aria-label="Filter by severity" value={severityFilter} onChange={event=>setSeverityFilter(event.target.value)}><option value="all">All severities</option><option value="blocking">Blocking</option><option value="review_required">Review required</option><option value="suggestion">Suggestion</option><option value="informational">Informational</option></select></label><label><span>Category</span><select aria-label="Filter by category" value={categoryFilter} onChange={event=>setCategoryFilter(event.target.value)}><option value="all">All categories</option>{categories.map(category=><option key={category} value={category}>{category.replaceAll("_"," ")}</option>)}</select></label><label><span>Verdict</span><select aria-label="Filter by verdict" value={verdictFilter} onChange={event=>setVerdictFilter(event.target.value)}><option value="all">All verdicts</option>{Array.from(new Set(findings.map(f=>f.verdict))).sort().map(verdict=><option key={verdict} value={verdict}>{verdict.replaceAll("_"," ")}</option>)}</select></label><label><span>Status</span><select aria-label="Filter by status" value={statusFilter} onChange={event=>setStatusFilter(event.target.value)}><option value="all">All statuses</option><option value="open">Open only</option><option value="resolved">Resolved only</option></select></label><label><span>Order</span><select aria-label="Sort findings" value={sortOrder} onChange={event=>setSortOrder(event.target.value)}><option value="risk">Risk first</option><option value="confidence-desc">Confidence: high to low</option><option value="confidence-asc">Confidence: low to high</option><option value="category">Category A–Z</option></select></label></div>{hasActiveFilters&&<button className="clear-filters" type="button" onClick={clearFindingFilters}><X size={13}/> Clear filters</button>}</div><div className="finding-list">{visibleFindings.length===0?<div className="filter-empty"><SlidersHorizontal size={21}/><b>No findings match these filters</b><span>Change your search or filter selections to see more results.</span><button className="text-link" type="button" onClick={clearFindingFilters}>Clear all filters</button></div>:visibleFindings.map(f=><FindingCard key={f.id} f={f} expanded={expanded===f.id} setExpanded={()=>setExpanded(expanded===f.id?null:f.id)} replacement={replacement[f.id]||f.suggestions?.[0]||""} setReplacement={value=>setReplacement(prev=>({...prev,[f.id]:value}))} onResolve={()=>resolveFinding(f)} onPatch={()=>applyPatch(f)} onLocate={()=>locateFinding(f)} canResolve={canDecide} canPatch={data.content_version.filename.toLowerCase().endsWith(".txt")} busy={busy}/>)}</div></>}</section>
 <aside className="review-side"><section className="panel evidence-panel"><div className="panel-heading"><div><div className="eyebrow">CONTENT SNAPSHOT</div><h2>Submitted text</h2></div><FileText size={17}/></div><div className="document-meta"><span>SHA-256</span><button className="copy-hash" onClick={()=>navigator.clipboard.writeText(data.content_version.sha256)}><code>{data.content_version.sha256.slice(0,16)}…</code><Copy size={12}/></button></div><HighlightedText text={data.content_version.text} findings={findings} activeFindingId={activeFindingId}/><div className="document-foot"><span><LockKeyhole size={13}/> Original preserved</span><span>v{data.content_version.version_number}</span></div></section>
 {previewError&&<div className="alert warning">{previewError}</div>}
 {previewUrl&&data.content_version.mime_type.startsWith("image/")&&<section className="panel original-panel" id="visual-region-inspector"><div className="panel-heading"><div><div className="eyebrow">ORIGINAL CREATIVE</div><h2>Visual evidence inspector</h2></div><span className="channel-tag">{data.content_version.regions.filter(region=>region.kind==="ocr_line").length} OCR regions</span></div><div style={{padding:16}}><ImageRegionViewer src={previewUrl} filename={data.content_version.filename} regions={data.content_version.regions} findings={findings} activeRegionId={activeRegionId} onSelectRegion={selectVisualRegion}/></div></section>}
 {previewUrl&&data.content_version.mime_type==="application/pdf"&&<section className="panel original-panel"><div className="panel-heading"><div><div className="eyebrow">ORIGINAL DOCUMENT</div><h2>PDF inspection</h2></div><span className="channel-tag">Source PDF</span></div><div style={{padding:16}}><iframe className="source-pdf-preview" src={previewUrl} title={`Original PDF: ${data.content_version.filename}`}/></div></section>}
 {previewUrl&&!data.content_version.mime_type.startsWith("image/")&&data.content_version.mime_type!=="application/pdf"&&<a className="button secondary" href={previewUrl} target="_blank" rel="noreferrer">Open original file: {data.content_version.filename}</a>}
 <section className="panel context-panel"><div className="eyebrow">GOVERNING CONTEXT</div><h2>Review basis</h2><Context label="Publication" value={new Date(data.submission.publication_at).toLocaleString()}/><Context label="Channel" value={data.submission.channel}/><Context label="Locale / geography" value={`${data.submission.locale} · ${data.submission.geography}`}/><Context label="Offer" value={data.submission.offer_id||"Not specified"}/><Context label="Intended use" value={(data.submission.intended_use||"general").replaceAll("_"," ")}/><Context label="Knowledge Pack" value={data.review.brand_pack_version}/><Context label="Knowledge Pack snapshot" value={data.review.knowledge_pack_hash.slice(0,18)+"…"}/><Context label="Analysis rules" value={data.review.analysis_config_version}/><Context label="Content hash" value={data.review.content_hash.slice(0,18)+"…"}/></section>
 <section className="panel version-history-panel"><div className="panel-heading"><div><div className="eyebrow">IMMUTABLE REVISION HISTORY</div><h2>{history.length} content versions</h2></div><History size={17}/></div>{history.length===0?<p className="panel-description">Version history is not available for this record.</p>:<div className="version-history-list">{history.map(item=><button key={item.version_id} type="button" className={`version-history-item ${item.version_id===data.content_version.id?"current":""}`} onClick={()=>item.review_id&&router.push(`/reviews/${item.review_id}`)} disabled={!item.review_id} aria-current={item.version_id===data.content_version.id?"page":undefined}><span className="version-history-mark">v{item.version_number}</span><span className="version-history-copy"><b>{item.filename}</b><small>{new Date(item.created_at).toLocaleString()} · {item.finding_count} findings</small><small>SHA-256 {item.sha256.slice(0,16)}…</small></span><span className="version-history-status">{item.decisions[0]?.action||item.review_status}</span></button>)}</div>}</section>
 {role==="creator"&&<section className="panel correction-panel"><div className="panel-heading"><div><div className="eyebrow">REVISION LOOP</div><h2>Submit a revised source</h2></div><span className="channel-tag">New immutable version</span></div><div style={{padding:18}}><p>Upload the corrected PDF, DOCX, TXT, PNG or JPG. Sigillum preserves the current version, creates the next version with a new SHA-256 hash and runs the checks again.</p><label>Revised source file<input type="file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,image/png,image/jpeg" onChange={event=>setRevisionFile(event.target.files?.[0]||null)}/></label><label>Change summary (optional)<textarea rows={2} value={revisionSummary} onChange={event=>setRevisionSummary(event.target.value)} placeholder="What changed in this revision?"/></label><button className="button primary" disabled={!revisionFile||revisionBusy} onClick={uploadRevision}>{revisionBusy?"Uploading and re-verifying…":"Upload revision & re-verify"}</button></div></section>}
 <section className="panel decision-panel"><div className="eyebrow">HUMAN DECISION</div><h2>Review & decide</h2><p>Approval applies only to this content hash and review context.</p>{!canDecide?<div className="alert warning">Your role can inspect the review but cannot record a decision. Sign in as a reviewer or brand owner.</div>:<><label>Decision reason <textarea value={reason} onChange={e=>setReason(e.target.value)} placeholder="Required for request changes, rejection or override…" rows={3}/></label><button className="button primary full" disabled={busy||blockers.length>0} onClick={()=>makeDecision("APPROVE")}><Check size={15}/> Approve exact version</button><div className="decision-secondary"><button className="button secondary" disabled={busy} onClick={()=>makeDecision("REQUEST_CHANGES")}>Request changes</button><button className="button danger" disabled={busy} onClick={()=>makeDecision("REJECT")}>Reject</button></div>{role!=="reviewer"&&<button className="text-link override-link" disabled={busy} onClick={()=>makeDecision("OVERRIDE")}>Record authorised override <ArrowRight size={14}/></button>}</>}{blockers.length>0&&<div className="block-reason"><ShieldAlert size={15}/><span>Approval is blocked until {blockers.length} blocking/review-required finding(s) are resolved or an authorised override is recorded.</span></div>}</section>
 {data.decisions.length>0&&<section className="panel decision-history"><div className="eyebrow">DECISION HISTORY</div><h2>Recorded actions</h2>{data.decisions.map(d=><div className="decision-entry" key={d.id}><span className="timeline-mark"><History size={14}/></span><span><b>{d.action.replaceAll("_"," ")}</b><small>{d.reason||"No reason supplied"}</small><small>{new Date(d.created_at).toLocaleString()}</small></span></div>)}</section>}</aside></div></div>;
}
function FindingCard({f,expanded,setExpanded,replacement,setReplacement,onResolve,onPatch,onLocate,canResolve,canPatch,busy}:{f:Finding;expanded:boolean;setExpanded:()=>void;replacement:string;setReplacement:(v:string)=>void;onResolve:()=>void;onPatch:()=>void;onLocate:()=>void;canResolve:boolean;canPatch:boolean;busy:boolean}){
 const state=f.status==="RESOLVED"?"success":f.severity==="blocking"?"danger":f.severity==="review_required"?"warning":"neutral";
 return <article id={`finding-card-${f.id}`} className={`finding-card ${expanded?"expanded":""}`}>
  <button className="finding-main" onClick={setExpanded} aria-expanded={expanded}>
   <span className={`finding-icon ${state}`}>{f.severity==="blocking"?<ShieldAlert size={17}/>:f.verdict==="SUPPORTED"?<CheckCircle2 size={17}/>:<AlertTriangle size={17}/>}</span>
   <span className="finding-copy"><span className="finding-meta"><span className={`status-pill ${state}`}><i/>{f.severity.replaceAll("_"," ")}</span><span className="category-label">{f.category}</span>{f.status==="RESOLVED"&&<span className="resolved-label">RESOLVED</span>}</span><b>{f.title}</b><small>{f.content_quote?`“${f.content_quote}” · `:""}{f.verdict.replaceAll("_"," ")}</small></span>
   <ChevronDown size={16} className={`expand-chevron ${expanded?"rotated":""}`}/>
  </button>
  {expanded&&<div className="finding-detail">
   <p>{f.explanation}</p>
   {f.content_quote&&<div className="quote-block"><span>EXACT CONTENT SPAN</span><b>{f.content_quote}</b><small>Characters {f.content_start}–{f.content_end}</small></div>}
   {f.content_start!==null&&f.content_end!==null&&<button className="text-link locate-link" type="button" onClick={onLocate}><Crosshair size={14}/> {f.region?.kind==="ocr_line"?"Locate OCR region in original creative":"Locate exact span in submitted text"}</button>}
   <div className="finding-facts"><div><small>VERDICT</small><b>{f.verdict}</b></div><div><small>EVIDENCE SUFFICIENCY</small><b>{f.evidence_sufficiency}</b></div><div><small>RULE CONFIDENCE</small><b>{Math.round(f.confidence*100)}%</b></div><div><small>EXTRACTION CONFIDENCE</small><b>{Math.round(f.extraction_confidence*100)}%</b></div><div><small>REASON CODE</small><b>{f.reason_code.replaceAll("_"," ")}</b></div><div><small>FINDING STATUS</small><b>{f.status.replaceAll("_"," ")}</b></div></div>
   {f.region&&<RegionDetails region={f.region}/>}
   {f.evidence.length>0&&<div className="evidence-block"><div className="eyebrow">SOURCE / RULE PROVENANCE</div>{f.evidence.map((e,i)=><EvidenceRow key={`${String(e.source_id||e.fact_id||e.term_id||e.policy_source||"evidence")}-${i}`} evidence={e}/>)}</div>}
   {f.suggestions?.filter(Boolean).length? <div className="patch-box"><div className="eyebrow">CONSTRAINED CORRECTION</div><p>Proposed text is a reversible suggestion. Verify the complete sentence and qualifiers before acceptance.</p><input value={replacement} onChange={e=>setReplacement(e.target.value)} aria-label="Replacement text"/>{canPatch?<button className="button secondary" disabled={busy||f.content_start===null} onClick={onPatch}><Sparkles size={14}/> Apply as new TXT version</button>:<div className="alert warning">For PDF, DOCX and image files, edit the original in its native tool, then upload the revised source above. Sigillum will not claim to edit a flattened asset.</div>}</div>:null}
   {canResolve&&f.status!=="RESOLVED"&&f.severity!=="informational"&&<button className="text-link resolve-link" disabled={busy} onClick={onResolve}><CheckCircle2 size={14}/> Mark reviewed with rationale</button>}
   {f.resolution_note&&<div className="resolution-note"><b>Resolution note</b><p>{f.resolution_note}</p></div>}
  </div>}
 </article>;
}
function HighlightedText({text,findings,activeFindingId}:{text:string;findings:Finding[];activeFindingId:string|null}){
 const spans=findings.filter(f=>f.content_start!==null&&f.content_end!==null&&f.content_end!>f.content_start!).sort((a,b)=>(a.content_start||0)-(b.content_start||0));
 const parts:React.ReactNode[]=[];let cursor=0;
 for(const f of spans){const start=f.content_start!;const end=f.content_end!;if(start<cursor||start>=text.length)continue;if(start>cursor)parts.push(text.slice(cursor,start));const active=f.id===activeFindingId;parts.push(<mark id={`finding-span-${f.id}`} key={f.id} className={`${f.severity==="blocking"?"mark-danger":"mark-warning"}${active?" mark-active":""}`} title={f.title}>{text.slice(start,end)}</mark>);cursor=end;}
 if(cursor<text.length)parts.push(text.slice(cursor));
 return <pre id="content-snapshot" className="document-text">{parts.length?parts:text||"No readable text was extracted from this asset."}</pre>;
}
function EvidenceRow({evidence}:{evidence:Record<string,unknown>}){
 const source=displayValue(evidence.source_id)||displayValue(evidence.fact_id)||displayValue(evidence.term_id)||displayValue(evidence.policy_source)||"Brand Knowledge Pack";
 const quote=displayValue(evidence.quote)||displayValue(evidence.reason)||displayValue(evidence.pattern)||"Approved source or deterministic rule";
 const sourceVersion=displayValue(evidence.source_version);
 const value=[displayValue(evidence.value),displayValue(evidence.unit),displayValue(evidence.qualifier)].filter(Boolean).join(" · ");
 const validity=[displayValue(evidence.valid_from),displayValue(evidence.valid_until)].filter(Boolean);
 const recorded=[displayValue(evidence.recorded_at),displayValue(evidence.recorded_until)].filter(Boolean);
 const scope=evidence.scope&&typeof evidence.scope==="object"&&!Array.isArray(evidence.scope)?Object.entries(evidence.scope as Record<string,unknown>).filter(([,v])=>v!==null&&v!==undefined&&v!=="").map(([k,v])=>`${k.replaceAll("_"," ")}: ${String(v)}`):[];
 const authority=displayValue(evidence.source_precedence)||displayValue(evidence.authority_rank);
 const temporalState=displayValue(evidence.temporal_state);
 const recordTimeState=displayValue(evidence.record_time_state);
 const retrievalMethod=displayValue(evidence.retrieval_method);
 const lexicalRank=displayValue(evidence.lexical_rank);const structuredRank=displayValue(evidence.structured_rank);
 const rrfScore=typeof evidence.rrf_score==="number"?evidence.rrf_score.toFixed(5):"";
 const diagnostic=evidence.eligible_for_proof===false;
 return <div className={`source-row ${diagnostic?"source-row-diagnostic":""}`}><span className="source-icon"><BookOpenIcon/></span><span className="source-row-content"><b>{source}</b>{diagnostic&&<small className="evidence-diagnostic-label">TEMPORAL DIAGNOSTIC — NOT USED AS PROOF</small>}<small>{quote}</small>{sourceVersion&&<small>Source version: {sourceVersion}</small>}{value&&<small>Approved value: {value}</small>}{validity.length>0&&<small>Valid time: {validity[0]} → {validity[1]||"open"}</small>}{recorded.length>0&&<small>Recorded time: {recorded[0]} → {recorded[1]||"current"}</small>}{scope.length>0&&<small>Scope: {scope.join(" · ")}</small>}{authority&&<small>Source precedence: {authority} (higher wins)</small>}{temporalState&&<small>Publication-time state: {temporalState}</small>}{recordTimeState&&<small>Knowledge-time state: {recordTimeState}</small>}{retrievalMethod&&<small>Retrieval: {retrievalMethod}{lexicalRank?` · lexical rank ${lexicalRank}`:""}{structuredRank?` · structured rank ${structuredRank}`:""}{rrfScore?` · RRF ${rrfScore}`:""}</small>}</span></div>;
}
function RegionDetails({region}:{region:Record<string,unknown>}){
 const kind=displayValue(region.kind);const page=displayValue(region.page);const confidence=displayValue(region.confidence);const regionId=displayValue(region.region_id);const bbox=region.bbox&&typeof region.bbox==="object"&&!Array.isArray(region.bbox)?region.bbox as Record<string,unknown>:null;
 const box=bbox?["x","y","width","height"].filter(key=>bbox[key]!==undefined).map(key=>`${key}: ${String(bbox[key])}`).join(" · "):"";
 const contrast=region.contrast&&typeof region.contrast==="object"&&!Array.isArray(region.contrast)?region.contrast as Record<string,unknown>:null;
 const contrastStatus=displayValue(contrast?.status);const contrastRatio=displayValue(contrast?.ratio);const contrastThreshold=displayValue(contrast?.threshold);
 const details=[kind,regionId,page?`page ${page}`:"",box?`pixel box ${box}`:"",confidence?`region confidence ${Math.round(Number(confidence)*100)}%`:""].filter(Boolean);
 if(details.length===0)return null;
 return <div className="region-details"><span>CONTENT LOCATION</span><b>{details.join(" · ")}</b>{contrast&&<small>Local contrast: {contrastStatus}{contrastRatio?` · ${contrastRatio}:1`:""}{contrastThreshold?` · threshold ${contrastThreshold}:1`:""} · manual confirmation required</small>}<small>Coordinates are shown only when supplied by extraction; no position is inferred.</small></div>;
}

function ImageRegionViewer({src,filename,regions,findings,activeRegionId,onSelectRegion}:{src:string;filename:string;regions:Array<Record<string,unknown>>;findings:Finding[];activeRegionId:string|null;onSelectRegion:(region:Record<string,unknown>)=>void}){
 const metadata=regions.find(region=>region.kind==="image_metadata")||{};
 const width=typeof metadata.width==="number"&&metadata.width>0?metadata.width:1200;
 const height=typeof metadata.height==="number"&&metadata.height>0?metadata.height:900;
 const ocrRegions=regions.filter(region=>region.kind==="ocr_line"&&region.bbox&&typeof region.bbox==="object");
 const palette=Array.isArray(metadata.palette)?metadata.palette.filter((item):item is Record<string,unknown>=>Boolean(item)&&typeof item==="object"&&!Array.isArray(item)):[];
 function points(region:Record<string,unknown>):string{
  if(Array.isArray(region.polygon))return region.polygon.filter((point):point is number[]=>Array.isArray(point)&&point.length>=2&&typeof point[0]==="number"&&typeof point[1]==="number").map(point=>`${point[0]},${point[1]}`).join(" ");
  const box=region.bbox as Record<string,unknown>;const x=Number(box.x),y=Number(box.y),w=Number(box.width),h=Number(box.height);
  return [ [x,y],[x+w,y],[x+w,y+h],[x,y+h] ].map(point=>point.join(",")).join(" ");
 }
 return <div className="visual-inspector-stack">
  <div className="image-region-stage" style={{aspectRatio:`${width} / ${height}`}}>
   <Image className="source-image-preview" src={src} alt={`Original submitted creative: ${filename}`} fill sizes="(max-width: 900px) 100vw, 50vw" unoptimized/>
   <svg className="image-region-overlay" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" role="group" aria-label="OCR text-region overlays">
    {ocrRegions.map(region=>{
     const regionId=displayValue(region.region_id);const linked=findings.find(f=>f.region?.region_id===regionId);const severity=linked?.severity||"neutral";const selected=activeRegionId===regionId;
     const text=displayValue(region.text)||`OCR region ${regionId}`;
     return <polygon key={regionId} className={`ocr-region-polygon ${severity} ${selected?"selected":""}`} points={points(region)} tabIndex={0} role="button" aria-label={`Select OCR region: ${text.slice(0,100)}`} onClick={()=>onSelectRegion(region)} onKeyDown={event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();onSelectRegion(region);}}}><title>{text}</title></polygon>;
    })}
   </svg>
  </div>
  <div className="visual-inspector-legend"><span><i className="legend-blocking"/> Blocking/review finding</span><span><i className="legend-neutral"/> Extracted text region</span><span>Click a region to inspect its OCR text and linked finding.</span></div>
  <div className="visual-inspector-summary"><div><span>IMAGE DIMENSIONS</span><b>{width} × {height} px</b></div><div><span>EXTRACTED REGIONS</span><b>{ocrRegions.length}</b></div><div><span>PIXEL FINGERPRINT</span><b>{displayValue(metadata.pixel_sha256).slice(0,16)||"Unavailable"}…</b></div></div>
  {palette.length>0&&<div className="palette-report"><div className="eyebrow">DOMINANT COLOUR INVENTORY</div><div className="palette-swatches">{palette.map((item,index)=><div className="palette-swatch" key={`${displayValue(item.hex)}-${index}`}><i style={{background:displayValue(item.hex)||"transparent"}}/><span>{displayValue(item.hex)} · {Math.round(Number(item.coverage||0)*100)}%</span></div>)}</div><small>{displayValue(metadata.palette_notice)||"Descriptive colour inventory; no brand compliance verdict is inferred."}</small></div>}
  {ocrRegions.length===0&&<div className="alert warning">No OCR polygons are available. Review the original creative manually; missing OCR geometry is not evidence that the image contains no relevant text.</div>}
  {activeRegionId&&(()=>{const selected=ocrRegions.find(region=>region.region_id===activeRegionId);if(!selected)return null;const contrast=selected.contrast&&typeof selected.contrast==="object"?selected.contrast as Record<string,unknown>:{};return <div className="selected-region-card"><div className="eyebrow">SELECTED OCR REGION · {activeRegionId}</div><b>{displayValue(selected.text)||"Text unavailable"}</b><small>Extraction confidence: {Math.round(Number(selected.confidence||0)*100)}%</small><small>Contrast: {displayValue(contrast.status)||"UNMEASURABLE"}{contrast.ratio?` · ${displayValue(contrast.ratio)}:1`:""}{contrast.threshold?` / ${displayValue(contrast.threshold)}:1 threshold`:""}</small>{findings.some(f=>f.region?.region_id===activeRegionId)&&<small>Linked finding: {findings.find(f=>f.region?.region_id===activeRegionId)?.title}</small>}</div>;})()}
  <small className="visual-inspector-disclaimer">Contrast values are conservative local estimates for individual OCR lines, require human confirmation and do not certify the complete creative or WCAG conformance.</small>
 </div>;
}
function displayValue(value:unknown):string{if(typeof value==="string")return value;if(typeof value==="number"||typeof value==="boolean")return String(value);return "";}
function Context({label,value}:{label:string;value:string}){return <div className="context-row"><span>{label}</span><b>{value}</b></div>}
function BookOpenIcon(){return <Info size={14}/>}
