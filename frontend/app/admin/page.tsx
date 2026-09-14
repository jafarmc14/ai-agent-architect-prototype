"use client";

import { Check, LogOut, MessageSquare, RefreshCw, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getAuthToken, signOut, type AuthUser } from "../../lib/auth";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type Approval = {
  confirmation_id: string;
  action: string;
  resource_id: string;
  order_status: string | null;
  actor_user_id: string;
  requester_name: string;
  created_at: string;
  expires_at: string;
};

function actionName(action: string) {
  return action === "order.cancel" ? "Cancel order" : "Change shipping address";
}

export default function AdminPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [busy, setBusy] = useState(true);
  const [deciding, setDeciding] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const token = getAuthToken();
    if (!token) { window.location.replace("/login"); return; }
    setBusy(true);
    setError("");
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const sessionResponse = await fetch(`${apiBaseUrl}/api/v1/auth/session`, { headers, cache: "no-store" });
      if (sessionResponse.status === 401) { signOut(); return; }
      if (!sessionResponse.ok) throw new Error("Could not verify your session.");
      const session = await sessionResponse.json() as AuthUser;
      if (!session.role || !["admin", "manager"].includes(session.role)) { window.location.replace("/orders"); return; }
      setUser(session);
      const response = await fetch(`${apiBaseUrl}/api/v1/governance/approvals`, { headers, cache: "no-store" });
      if (response.status === 401) { signOut(); return; }
      if (!response.ok) throw new Error("Could not load approvals.");
      setApprovals(await response.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load approvals.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function decide(item: Approval, decision: "approve" | "reject") {
    const verb = decision === "approve" ? "Approve" : "Not approve";
    if (!window.confirm(`${verb} ${actionName(item.action).toLowerCase()} for ${item.resource_id}, requested by ${item.requester_name}?`)) return;
    const token = getAuthToken();
    if (!token) { signOut(); return; }
    setDeciding(item.confirmation_id);
    setNotice("");
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/governance/approvals/${item.confirmation_id}/${decision}`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }
      });
      if (response.status === 401) { signOut(); return; }
      if (!response.ok) throw new Error("Decision unavailable. Check the requester, expiry, or current request state.");
      setNotice(decision === "approve"
        ? `${item.resource_id} approved. The requester must complete the action in chat.`
        : `${item.resource_id} not approved. No order change was made.`);
      setApprovals((current) => current.filter((entry) => entry.confirmation_id !== item.confirmation_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Decision failed.");
    } finally {
      setDeciding("");
    }
  }

  return (
    <main className="min-h-screen bg-surface-950 text-ink">
      <header className="border-b border-line bg-surface-900">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div><p className="text-xs text-faint">Ubichinon · {user?.role ?? "Admin"}</p><h1 className="text-lg font-semibold">Approvals</h1></div>
          <div className="flex items-center gap-3 text-sm text-muted">
            <span className="max-w-[180px] truncate">{user?.name || user?.email || "Admin"}</span>
            <Link href="/" title="Assistant" aria-label="Assistant" className="grid h-8 w-8 place-items-center rounded-md hover:bg-surface-850 hover:text-ink"><MessageSquare size={16} /></Link>
            <button type="button" onClick={() => void load()} title="Refresh" aria-label="Refresh" className="grid h-8 w-8 place-items-center rounded-md hover:bg-surface-850 hover:text-ink"><RefreshCw size={16} /></button>
            <button type="button" onClick={signOut} title="Sign out" aria-label="Sign out" className="grid h-8 w-8 place-items-center rounded-md hover:bg-surface-850 hover:text-ink"><LogOut size={16} /></button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-5 py-8">
        {notice ? <p role="status" className="mb-5 text-sm text-success">{notice}</p> : null}
        {error ? <p role="alert" className="mb-5 text-sm text-danger-action">{error}</p> : null}
        <h2 className="mb-4 text-sm font-semibold text-muted">Waiting for review</h2>
        <div className="overflow-x-auto border-y border-line">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-surface-900 text-xs text-faint"><tr><th className="px-3 py-3 font-medium">Order</th><th className="px-3 py-3 font-medium">Status</th><th className="px-3 py-3 font-medium">Action</th><th className="px-3 py-3 font-medium">Requested by</th><th className="px-3 py-3 font-medium">Expires</th><th className="px-3 py-3 text-right font-medium">Decision</th></tr></thead>
            <tbody className="divide-y divide-line">
              {approvals.map((item) => <tr key={item.confirmation_id}>
                  <td className="px-3 py-3 font-medium">{item.resource_id}</td>
                  <td className="px-3 py-3 text-muted">{item.order_status?.replaceAll("_", " ") ?? "Unknown"}</td>
                  <td className="px-3 py-3 text-muted">{actionName(item.action)}</td>
                <td className="px-3 py-3 text-muted">{item.requester_name}</td>
                <td className="px-3 py-3 text-muted">{new Date(item.expires_at).toLocaleString()}</td>
                  <td className="px-3 py-3 text-right">{item.actor_user_id === user?.id
                  ? <span className="text-xs text-faint">Own request</span>
                  : <div className="flex justify-end gap-2">
                      <button type="button" disabled={Boolean(deciding)} onClick={() => void decide(item, "approve")}
                        className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-sm text-ink hover:bg-surface-850 disabled:opacity-40"><Check size={14} /> Approve</button>
                      <button type="button" disabled={Boolean(deciding)} onClick={() => void decide(item, "reject")}
                        className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-sm text-muted hover:bg-surface-850 hover:text-ink disabled:opacity-40"><X size={14} /> Not approve</button>
                    </div>}</td>
              </tr>)}
            </tbody>
          </table>
          {!busy && !approvals.length ? <p className="px-3 py-6 text-sm text-muted">No requests waiting for review.</p> : null}
        </div>
      </div>
    </main>
  );
}
