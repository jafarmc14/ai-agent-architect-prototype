"use client";

import { ArrowLeft, LogOut, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getAuthToken, signOut, type AuthUser } from "../../lib/auth";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type Order = { id: string; status: string; total: string; currency: string; order_date: string };
type ActionRequest = {
  confirmation_id: string;
  action: string;
  order_id: string;
  state: string;
  created_at: string;
  expires_at: string;
};

function amount(order: Order) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: order.currency }).format(Number(order.total));
}

function actionName(action: string) {
  return action === "order.cancel" ? "Cancel order" : "Change shipping address";
}

export default function MyOrdersPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [requests, setRequests] = useState<ActionRequest[]>([]);
  const [busy, setBusy] = useState(true);
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
      if (session.role !== "customer") { window.location.replace("/admin"); return; }
      setUser(session);
      const [ordersResponse, requestsResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/v1/orders/mine`, { headers, cache: "no-store" }),
        fetch(`${apiBaseUrl}/api/v1/order-action-requests`, { headers, cache: "no-store" })
      ]);
      if (ordersResponse.status === 401 || requestsResponse.status === 401) { signOut(); return; }
      if (!ordersResponse.ok || !requestsResponse.ok) throw new Error("Could not load your orders. Please retry.");
      setOrders(await ordersResponse.json());
      setRequests(await requestsResponse.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load your orders.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void load(); }, []);

  return (
    <main className="min-h-screen bg-surface-950 text-ink">
      <header className="border-b border-line bg-surface-900">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="grid h-8 w-8 place-items-center rounded-md text-muted hover:bg-surface-850 hover:text-ink" title="Back to assistant" aria-label="Back to assistant"><ArrowLeft size={17} /></Link>
            <div><p className="text-xs text-faint">Ubichinon</p><h1 className="text-lg font-semibold">My orders</h1></div>
          </div>
          <div className="flex items-center gap-3 text-sm text-muted">
            <span className="max-w-[180px] truncate">{user?.name || user?.email || "Customer"}</span>
            <button type="button" onClick={() => void load()} title="Refresh" aria-label="Refresh" className="grid h-8 w-8 place-items-center rounded-md hover:bg-surface-850 hover:text-ink"><RefreshCw size={16} /></button>
            <button type="button" onClick={signOut} title="Sign out" aria-label="Sign out" className="grid h-8 w-8 place-items-center rounded-md hover:bg-surface-850 hover:text-ink"><LogOut size={16} /></button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-5 py-8">
        {error ? <p role="alert" className="mb-5 text-sm text-danger-action">{error}</p> : null}
        <section aria-labelledby="orders-title">
          <h2 id="orders-title" className="mb-4 text-sm font-semibold text-muted">Orders</h2>
          <div className="overflow-x-auto border-y border-line">
            <table className="w-full min-w-[540px] text-left text-sm">
              <thead className="bg-surface-900 text-xs text-faint"><tr><th className="px-3 py-3 font-medium">Order</th><th className="px-3 py-3 font-medium">Date</th><th className="px-3 py-3 font-medium">Status</th><th className="px-3 py-3 text-right font-medium">Total</th><th className="px-3 py-3" /></tr></thead>
              <tbody className="divide-y divide-line">
                {orders.map((order) => <tr key={order.id}>
                  <td className="px-3 py-3 font-medium">{order.id}</td>
                  <td className="px-3 py-3 text-muted">{new Date(order.order_date).toLocaleDateString()}</td>
                  <td className="px-3 py-3 text-muted">{order.status}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{amount(order)}</td>
                  <td className="px-3 py-3 text-right"><Link href={`/?draft=${encodeURIComponent(`Check order ${order.id}`)}`} className="text-brand-action hover:underline">Ask</Link></td>
                </tr>)}
              </tbody>
            </table>
            {!busy && !orders.length ? <p className="px-3 py-6 text-sm text-muted">No orders found for this account.</p> : null}
          </div>
        </section>

        <section aria-labelledby="requests-title" className="mt-10">
          <h2 id="requests-title" className="mb-4 text-sm font-semibold text-muted">Change requests</h2>
          <div className="divide-y divide-line border-y border-line">
            {requests.map((request) => <div key={request.confirmation_id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-3 text-sm">
              <div><p className="font-medium">{actionName(request.action)} · {request.order_id}</p><p className="mt-1 text-xs text-faint">{request.confirmation_id}</p></div>
              <div className="flex items-center gap-4"><span className="text-muted">{request.state === "rejected" ? "Not approved" : request.state.replaceAll("_", " ")}</span>
                {request.state === "approved" || request.state === "waiting_confirmation" ? <Link href={`/?draft=${encodeURIComponent(`confirm ${request.confirmation_id}`)}`} className="text-brand-action hover:underline">Continue in chat</Link> : null}
              </div>
            </div>)}
            {!busy && !requests.length ? <p className="px-3 py-6 text-sm text-muted">No change requests.</p> : null}
          </div>
        </section>
      </div>
    </main>
  );
}
