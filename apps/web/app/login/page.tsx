"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ScanEye, ShieldCheck } from "lucide-react";
import { API_BASE, saveSession, type WorkspaceOption } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("creator@orbita.demo");
  const [password, setPassword] = useState("ChangeMe-Local-Only");
  const [workspaces, setWorkspaces] = useState<WorkspaceOption[]>([]);
  const [selectedBrandId, setSelectedBrandId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const payload: { email: string; password: string; brand_id?: string } = { email, password };
      if (selectedBrandId) payload.brand_id = selectedBrandId;
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 409 && data?.detail?.code === "WORKSPACE_SELECTION_REQUIRED") {
          const choices = (data.detail.workspaces || []) as WorkspaceOption[];
          setWorkspaces(choices);
          setSelectedBrandId(choices[0]?.brand_record_id || "");
          setError("Select the workspace and brand you want to enter, then sign in again.");
          return;
        }
        throw new Error(data?.detail?.message || "Sign in failed");
      }
      saveSession(data.access_token, { ...data.user, workspaces: data.workspaces || [] });
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to sign in");
    } finally {
      setLoading(false);
    }
  }

  function updateEmail(value: string) {
    setEmail(value);
    setWorkspaces([]);
    setSelectedBrandId("");
  }

  return (
    <div className="login-screen">
      <div className="login-art">
        <div className="login-orbit orbit-a" />
        <div className="login-orbit orbit-b" />
        <div className="login-orbit orbit-c" />
        <div className="login-art-content">
          <div className="brand-lockup large">
            <span className="brand-mark"><ScanEye size={25} /></span>
            <span><b>INKLOOM</b><small>SIGILLUM</small></span>
          </div>
          <p className="eyebrow">EVIDENCE · CONTROL · ACCOUNTABILITY</p>
          <h1>Brand truth,<br /><em>verified</em> before it ships.</h1>
          <p className="login-copy">An assurance layer between content creation and publication. Every material finding has a trail. Every consequential decision has an owner.</p>
          <div className="login-proof">
            <span><ShieldCheck size={15} /> SOURCE-LINKED FINDINGS</span>
            <span><ShieldCheck size={15} /> DETERMINISTIC POLICY</span>
            <span><ShieldCheck size={15} /> HUMAN APPROVAL</span>
          </div>
        </div>
        <div className="login-art-footer">DEVIL UNION <i>·</i> PRODUCT ENGINEERING <i>·</i> 2026</div>
      </div>
      <div className="login-panel">
        <form className="login-form" onSubmit={submit}>
          <div className="eyebrow">SECURE WORKSPACE</div>
          <h2>Welcome back.</h2>
          <p>Sign in to your brand assurance workspace.</p>
          <label>Email address
            <input type="email" value={email} onChange={(e) => updateEmail(e.target.value)} required autoComplete="username" />
          </label>
          <label>Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
          </label>
          {workspaces.length > 1 && (
            <label>Workspace and brand
              <select value={selectedBrandId} onChange={(e) => setSelectedBrandId(e.target.value)} required>
                {workspaces.map((workspace) => (
                  <option key={workspace.membership_id} value={workspace.brand_record_id}>
                    {workspace.tenant_name} · {workspace.brand_name} · {workspace.role.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
          )}
          {error && <div className="alert error">{error}</div>}
          <button className="button primary full" disabled={loading || (workspaces.length > 1 && !selectedBrandId)}>
            {loading ? "Signing in…" : "Enter workspace"}<ArrowRight size={16} />
          </button>
          <div className="demo-note"><span className="pulse-dot" /> LOCAL DEMO ACCOUNTS ENABLED</div>
          <div className="demo-roles">
            <button type="button" onClick={() => updateEmail("creator@orbita.demo")}>Creator</button>
            <button type="button" onClick={() => updateEmail("reviewer@orbita.demo")}>Reviewer</button>
            <button type="button" onClick={() => updateEmail("owner@orbita.demo")}>Brand owner</button>
            <button type="button" onClick={() => updateEmail("admin@orbita.demo")}>Admin</button>
          </div>
          <small className="login-footnote">The shared demo password is configured in the backend environment file. Change it before deployment.</small>
        </form>
      </div>
    </div>
  );
}
