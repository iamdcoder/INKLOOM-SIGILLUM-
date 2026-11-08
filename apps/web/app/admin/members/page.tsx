"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { RefreshCw, ShieldCheck, UserPlus, Users } from "lucide-react";
import { api, getSessionUserRaw, parseSessionUser, subscribeToSession } from "@/lib/api";

type MembershipRow = {
  membership_id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
};

const ADMIN_ROLES = ["creator", "agency", "reviewer", "brand_owner", "administrator"];
const OWNER_ROLES = ["creator", "agency", "reviewer"];

export default function WorkspaceMembersPage() {
  const sessionSnapshot = useSyncExternalStore(subscribeToSession, getSessionUserRaw, () => null);
  const user = useMemo(() => parseSessionUser(sessionSnapshot), [sessionSnapshot]);
  const canManage = user?.role === "administrator" || user?.role === "brand_owner";
  const isAdmin = user?.role === "administrator";
  const assignableRoles = isAdmin ? ADMIN_ROLES : OWNER_ROLES;

  const [members, setMembers] = useState<MembershipRow[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("creator");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const rows = await api<MembershipRow[]>("/workspace/memberships");
      setMembers(rows);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load workspace memberships.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (canManage) void refresh();
    else setLoading(false);
  }, [canManage, refresh]);

  async function addMember(event: FormEvent) {
    event.preventDefault();
    setBusyId("new");
    setError("");
    setNotice("");
    try {
      await api("/workspace/memberships", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), role }),
      });
      setEmail("");
      setNotice(`${email.trim()} was added to this brand workspace as ${role.replaceAll("_", " ")}.`);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add this workspace member.");
    } finally {
      setBusyId("");
    }
  }

  async function updateMember(member: MembershipRow, patch: { role?: string; is_active?: boolean }) {
    setBusyId(member.membership_id);
    setError("");
    setNotice("");
    try {
      await api(`/workspace/memberships/${member.membership_id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setNotice(`Membership updated for ${member.email}.`);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update this membership.");
    } finally {
      setBusyId("");
    }
  }

  if (!canManage) {
    return (
      <div className="page-stack">
        <section className="hero-row"><div><div className="eyebrow">WORKSPACE ADMINISTRATION</div><h1>Workspace access</h1><p className="subhead">Membership controls are restricted to authorised workspace administrators and brand owners.</p></div></section>
        <div className="alert error" role="alert">Your current workspace role cannot manage memberships.</div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <section className="hero-row">
        <div>
          <div className="eyebrow">IDENTITY & ACCESS GOVERNANCE</div>
          <h1>Workspace access</h1>
          <p className="subhead">Manage who can work inside {user?.brand_name || "this brand"}. Access is granted per brand membership, not by a global user role.</p>
        </div>
        <span className="security-chip"><ShieldCheck size={14}/> DEFAULT-DENY ACCESS</span>
      </section>

      {error && <div className="alert error" role="alert">{error}</div>}
      {notice && <div className="alert success" role="status">{notice}</div>}

      <section className="panel form-panel">
        <div className="panel-heading">
          <div><div className="eyebrow">ADD AN EXISTING ACCOUNT</div><h2>Grant brand membership</h2></div>
          <UserPlus size={18}/>
        </div>
        <p className="panel-description">The account must already exist. Email invitations and account creation are not part of this build yet. New membership access takes effect on the next authenticated request.</p>
        <form className="member-add-form" onSubmit={addMember}>
          <label>Email address<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="person@organisation.com" /></label>
          <label>Workspace role<select value={role} onChange={(event) => setRole(event.target.value)}>{assignableRoles.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select></label>
          <button className="button primary" disabled={busyId === "new" || !email.trim()}><UserPlus size={14}/>{busyId === "new" ? "Adding…" : "Add member"}</button>
        </form>
      </section>

      <section className="panel member-list-panel">
        <div className="panel-heading">
          <div><div className="eyebrow">CURRENT BRAND MEMBERS</div><h2>{members.length} memberships</h2></div>
          <button type="button" className="button secondary member-refresh" onClick={() => void refresh()} disabled={loading}><RefreshCw size={14}/>Refresh</button>
        </div>
        {loading ? <div className="empty-state">Loading workspace memberships…</div> : members.length === 0 ? <div className="empty-state"><Users size={25}/><h3>No members found</h3><p>Accounts added to this brand will appear here.</p></div> : (
          <div className="table-wrap">
            <table className="member-table">
              <thead><tr><th>Member</th><th>Role</th><th>Status</th><th>Access</th></tr></thead>
              <tbody>{members.map((member) => (
                <tr key={member.membership_id}>
                  <td><b>{member.display_name}</b><small>{member.email}</small></td>
                  <td>
                    {isAdmin ? (
                      <select aria-label={`Role for ${member.email}`} value={member.role} disabled={busyId === member.membership_id} onChange={(event) => void updateMember(member, { role: event.target.value })}>
                        {ADMIN_ROLES.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
                      </select>
                    ) : <span className="member-role">{member.role.replaceAll("_", " ")}</span>}
                  </td>
                  <td><span className={`member-state ${member.is_active ? "active" : "inactive"}`}>{member.is_active ? "ACTIVE" : "INACTIVE"}</span></td>
                  <td>{isAdmin ? (
                    <button type="button" className={`button ${member.is_active ? "danger" : "secondary"} member-action`} disabled={busyId === member.membership_id} onClick={() => void updateMember(member, { is_active: !member.is_active })}>
                      {busyId === member.membership_id ? "Saving…" : member.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                  ) : <span className="table-secondary">Administrator controlled</span>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        <p className="panel-description member-footnote">Administrators can change roles and activate/deactivate memberships. Brand owners can add creator, agency and reviewer memberships only. The last active administrator cannot be removed or demoted.</p>
      </section>
    </div>
  );
}
