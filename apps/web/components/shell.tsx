"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { ArrowUpRight, BookOpen, Command, FilePlus2, Files, LayoutDashboard, LogOut, ScanEye, ShieldCheck, Users } from "lucide-react";
import { api, clearSession, getSessionUserRaw, parseSessionUser, saveSession, subscribeToSession, type SessionUser, type WorkspaceOption } from "@/lib/api";

const navigation = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/submissions", label: "Submissions", icon: Files },
  { href: "/submissions/new", label: "New review", icon: FilePlus2 },
  { href: "/brand", label: "Brand Control Center", icon: BookOpen },
  { href: "/audit", label: "Governance & audit", icon: ShieldCheck },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const userSnapshot = useSyncExternalStore(
    subscribeToSession,
    getSessionUserRaw,
    () => null,
  );
  const user = useMemo(() => parseSessionUser(userSnapshot), [userSnapshot]);
  const [switchingWorkspace, setSwitchingWorkspace] = useState(false);
  const [workspaceSwitchError, setWorkspaceSwitchError] = useState("");
  const visibleNavigation = user && ["brand_owner", "administrator"].includes(user.role)
    ? [...navigation, { href: "/admin/members", label: "Workspace access", icon: Users }]
    : navigation;

  useEffect(() => {
    if (pathname === "/login") return;
    if (!sessionStorage.getItem("sigillum_token")) {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    api("/auth/me").catch(() => {
      if (!cancelled) {
        clearSession();
        router.replace("/login");
      }
    });
    return () => { cancelled = true; };
  }, [pathname, router, userSnapshot]);
  const switchWorkspace = async (brandRecordId: string) => {
    if (!brandRecordId || brandRecordId === user?.brand_record_id || switchingWorkspace) return;
    setSwitchingWorkspace(true);
    setWorkspaceSwitchError("");
    try {
      const result = await api<{ access_token: string; user: SessionUser; workspaces: WorkspaceOption[] }>(
        "/auth/switch-context",
        { method: "POST", body: JSON.stringify({ brand_id: brandRecordId }) },
      );
      saveSession(result.access_token, { ...result.user, workspaces: result.workspaces || [] });
      router.replace("/");
    } catch (error) {
      setWorkspaceSwitchError(error instanceof Error ? error.message : "Unable to switch workspace.");
    } finally {
      setSwitchingWorkspace(false);
    }
  };
  const logout = async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* local session is still cleared if the API is unavailable */ }
    finally { clearSession(); router.replace("/login"); }
  };
  if (pathname === "/login") return <>{children}</>;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand-lockup">
          <span className="brand-mark"><ScanEye size={21}/></span>
          <span><b>INKLOOM</b><small>SIGILLUM</small></span>
        </Link>
        <div className="workspace-switch">
          <span className="workspace-dot"/>
          <span className="workspace-switch-label"><b>{user?.brand_name || "Brand workspace"}</b><small>{user?.tenant_name || "Workspace"}</small></span>
          {user?.workspaces && user.workspaces.length > 1 ? (
            <select
              className="workspace-selector"
              aria-label="Switch workspace and brand"
              value={user.brand_record_id || ""}
              disabled={switchingWorkspace}
              onChange={(event) => void switchWorkspace(event.target.value)}
            >
              {user.workspaces.map((workspace) => (
                <option key={workspace.membership_id} value={workspace.brand_record_id}>
                  {workspace.tenant_name} · {workspace.brand_name}
                </option>
              ))}
            </select>
          ) : <ArrowUpRight size={14}/>}
          {workspaceSwitchError && <small className="workspace-switch-error" role="alert">{workspaceSwitchError}</small>}
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav-list">{visibleNavigation.map((item) => {
          const Icon = item.icon; const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return <Link key={item.href} href={item.href} className={`nav-link ${active ? "active" : ""}`}><Icon size={17}/><span>{item.label}</span>{item.href === "/submissions" && <span className="nav-count">LIVE</span>}</Link>;
        })}</nav>
        <div className="sidebar-bottom">
          <div className="system-card"><div className="system-line"><span className="pulse-dot"/> CORE API ACTIVE</div><p>Local review API available</p><small>Knowledge Pack v1.0.0-demo</small></div>
          <div className="profile-row"><div className="avatar">{user?.display_name?.slice(0,1) || "S"}</div><div className="profile-meta"><b>{user?.display_name || "Sigillum user"}</b><small>{user?.role?.replaceAll("_", " ") || "Checking session"}</small></div><button className="icon-button" aria-label="Sign out" onClick={logout}><LogOut size={16}/></button></div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar"><div className="breadcrumb"><span>Workspace</span><span className="slash">/</span><b>{pathname === "/" ? "Overview" : pathname.split("/").filter(Boolean).join(" / ") || "Overview"}</b></div><div className="topbar-right"><span className="security-chip"><ShieldCheck size={14}/> HUMAN-GOVERNED</span><button className="command-button" onClick={() => router.push("/submissions/new")}><Command size={14}/> <span>New review</span><kbd>⌘ K</kbd></button></div></header>
        <div className="page-content">{children}</div>
        <footer className="app-footer"><span>INKLOOM SIGILLUM <i>·</i> Evidence-first brand assurance</span><span>DEMO ENVIRONMENT <i>·</i> SYNTHETIC BRAND DATA</span></footer>
      </main>
    </div>
  );
}
