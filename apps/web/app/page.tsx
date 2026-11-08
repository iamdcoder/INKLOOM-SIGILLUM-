"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, ArrowRight, Clock3, FileCheck2, FilePlus2, Files, ShieldAlert, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
type Summary={submissions:number;needs_review:number;approved:number;findings:number;brand_name:string};
type Submission={id:string;title:string;status:string;channel:string;created_at:string;filename:string|null;version:number|null};
const fmt=(value:string)=>new Date(value).toLocaleString("en-IN",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"});
export default function Dashboard() {
 const [summary,setSummary]=useState<Summary|null>(null); const [items,setItems]=useState<Submission[]>([]); const [error,setError]=useState("");
 useEffect(()=>{Promise.all([api<Summary>("/dashboard/summary"),api<Submission[]>("/submissions")]).then(([s,i])=>{setSummary(s);setItems(i)}).catch(e=>setError(e.message));},[]);
 return <div className="page-stack">
  <section className="hero-row"><div><div className="eyebrow">BRAND WORKSPACE <span className="eyebrow-dot"/> PRE-PUBLICATION ASSURANCE</div><h1>Good afternoon.</h1><p className="subhead">Here’s the current assurance pulse across your content.</p></div><Link href="/submissions/new" className="button primary"><FilePlus2 size={16}/> New submission <ArrowUpRight size={15}/></Link></section>
  <section className="metric-grid">
   <article className="metric-card"><div className="metric-top"><span>TOTAL SUBMISSIONS</span><Files size={17}/></div><strong>{summary?.submissions ?? "—"}</strong><small>Across this workspace</small></article>
   <article className="metric-card warning"><div className="metric-top"><span>AWAITING REVIEW</span><Clock3 size={17}/></div><strong>{summary?.needs_review ?? "—"}</strong><small>Human attention required</small></article>
   <article className="metric-card success"><div className="metric-top"><span>APPROVED</span><ShieldCheck size={17}/></div><strong>{summary?.approved ?? "—"}</strong><small>Version-bound decisions</small></article>
   <article className="metric-card"><div className="metric-top"><span>FINDINGS RAISED</span><ShieldAlert size={17}/></div><strong>{summary?.findings ?? "—"}</strong><small>Source-linked observations</small></article>
  </section>
  <section className="dashboard-grid">
   <div className="panel submissions-panel"><div className="panel-heading"><div><div className="eyebrow">WORK QUEUE</div><h2>Recent submissions</h2></div><Link href="/submissions" className="text-link">View all <ArrowRight size={14}/></Link></div>
    {error?<div className="alert error">{error}</div>:items.length===0?<div className="empty-state"><div className="empty-icon"><Files size={24}/></div><h3>No submissions yet</h3><p>Start with a document or creative asset. Sigillum will preserve the original and create a version-bound review.</p><Link href="/submissions/new" className="button secondary">Create first review <ArrowRight size={15}/></Link></div>:<div className="table-wrap"><table><thead><tr><th>SUBMISSION</th><th>CHANNEL</th><th>STATUS</th><th>CREATED</th><th></th></tr></thead><tbody>{items.slice(0,7).map(item=><tr key={item.id}><td><Link href={`/reviews/${item.id}`} className="submission-name"><span className="file-icon"><FileCheck2 size={16}/></span><span><b>{item.title}</b><small>{item.filename || "No file"} · v{item.version || 1}</small></span></Link></td><td><span className="channel-tag">{item.channel.replaceAll("_"," ")}</span></td><td><Status status={item.status}/></td><td className="date-cell">{fmt(item.created_at)}</td><td><Link href={`/reviews/${item.id}`} className="arrow-link"><ArrowUpRight size={16}/></Link></td></tr>)}</tbody></table></div>}
   </div>
   <aside className="right-rail">
    <div className="panel assurance-card"><div className="panel-heading"><div><div className="eyebrow">SYSTEM INTEGRITY</div><h2>Assurance health</h2></div><span className="status-dot green"/></div><div className="health-status"><div className="health-symbol"><ShieldCheck size={26}/></div><div><b>Core application connected</b><small>Dashboard and review API are responding</small></div></div><div className="health-row"><span>API availability</span><b className="text-green">CONNECTED</b></div><div className="health-row"><span>Brand Knowledge Pack</span><b>v1.0.0-demo</b></div><div className="health-row"><span>Decision authority</span><b>HUMAN</b></div></div>
    <div className="insight-card"><div className="insight-icon"><Sparkles size={18}/></div><div className="eyebrow">CORE PRINCIPLE</div><h3>No proof.<br/>No SUPPORTED.</h3><p>Similarity is not substantiation. Only applicable approved evidence can support a decisive factual verdict.</p><Link href="/brand" className="text-link">Inspect Knowledge Pack <ArrowUpRight size={14}/></Link></div>
   </aside>
  </section>
  <section className="principles-strip"><div><ShieldCheck size={17}/><span><b>Evidence first</b><small>Every finding has provenance</small></span></div><div><TrendingUp size={17}/><span><b>Scope and time aware</b><small>Truth depends on context</small></span></div><div><FileCheck2 size={17}/><span><b>Immutable history</b><small>Edits create new versions</small></span></div><div><ShieldAlert size={17}/><span><b>Human authority</b><small>No autonomous publishing</small></span></div></section>
 </div>;
}
function Status({status}:{status:string}){const cls=status==="APPROVED"?"success":status==="NEEDS_REVIEW"?"warning":status==="REJECTED"?"danger":"neutral";return <span className={`status-pill ${cls}`}><i/>{status.replaceAll("_"," ")}</span>}
