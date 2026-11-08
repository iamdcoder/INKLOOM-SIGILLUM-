"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ScanEye, ShieldCheck } from "lucide-react";
import { API_BASE, saveSession } from "@/lib/api";
export default function LoginPage() {
  const router = useRouter();
  const [email,setEmail]=useState("creator@orbita.demo");
  const [password,setPassword]=useState("ChangeMe-Local-Only");
  const [error,setError]=useState(""); const [loading,setLoading]=useState(false);
  async function submit(event:FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const response=await fetch(`${API_BASE}/auth/login`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
      const data=await response.json(); if(!response.ok) throw new Error(data?.detail?.message || "Sign in failed");
      saveSession(data.access_token,data.user); router.replace("/");
    } catch(e) { setError(e instanceof Error ? e.message : "Unable to sign in"); }
    finally { setLoading(false); }
  }
  return <div className="login-screen"><div className="login-art"><div className="login-orbit orbit-a"/><div className="login-orbit orbit-b"/><div className="login-orbit orbit-c"/><div className="login-art-content"><div className="brand-lockup large"><span className="brand-mark"><ScanEye size={25}/></span><span><b>INKLOOM</b><small>SIGILLUM</small></span></div><p className="eyebrow">EVIDENCE · CONTROL · ACCOUNTABILITY</p><h1>Brand truth,<br/><em>verified</em> before it ships.</h1><p className="login-copy">An assurance layer between content creation and publication. Every material finding has a trail. Every consequential decision has an owner.</p><div className="login-proof"><span><ShieldCheck size={15}/> SOURCE-LINKED FINDINGS</span><span><ShieldCheck size={15}/> DETERMINISTIC POLICY</span><span><ShieldCheck size={15}/> HUMAN APPROVAL</span></div></div><div className="login-art-footer">DEVIL UNION <i>·</i> PRODUCT ENGINEERING <i>·</i> 2026</div></div><div className="login-panel"><form className="login-form" onSubmit={submit}><div className="eyebrow">SECURE WORKSPACE</div><h2>Welcome back.</h2><p>Sign in to your ORBITA brand assurance workspace.</p><label>Email address<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required autoComplete="username"/></label><label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} required autoComplete="current-password"/></label>{error&&<div className="alert error">{error}</div>}<button className="button primary full" disabled={loading}>{loading?"Signing in…":"Enter workspace"}<ArrowRight size={16}/></button><div className="demo-note"><span className="pulse-dot"/> LOCAL DEMO ACCOUNTS ENABLED</div><div className="demo-roles"><button type="button" onClick={()=>setEmail("creator@orbita.demo")}>Creator</button><button type="button" onClick={()=>setEmail("reviewer@orbita.demo")}>Reviewer</button><button type="button" onClick={()=>setEmail("owner@orbita.demo")}>Brand owner</button><button type="button" onClick={()=>setEmail("admin@orbita.demo")}>Admin</button></div><small className="login-footnote">The shared demo password is configured in the backend environment file. Change it before deployment.</small></form></div></div>;
}
