"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Activity, Archive, ArrowUpRight, BadgeCheck, BookOpen, Command, FilePlus2, Files, LayoutDashboard, LogOut, ScanEye, ShieldCheck, Workflow } from "lucide-react";
import { clearSession, getUser, SessionUser } from "@/lib/api";

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
  const [user, setUser] = useState<SessionUser | null>(null);
  useEffect(() => {
    setUser(getUser());
    if (pathname !== "/login" && !sessionStorage.getItem("sigillum_token")) router.replace("/login");
  }, [pathname, router]);
  const logout = () => { clearSession(); router.replace("/login"); };
  if (pathname === "/login") return <>{children}</>;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand-lockup">
          <span className="brand-mark"><ScanEye size={21}/></span>
          <span><b>INKLOOM</b><small>SIGILLUM</small></span>
        </Link>
        <div className="workspace-switch"><span className="workspace-dot"/><span><b>ORBITA</b><small>Demo workspace · 1 brand</small></span><ArrowUpRight size={14}/></div>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav-list">{navigation.map((item) => {
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
