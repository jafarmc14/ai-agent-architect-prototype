"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { getAuthToken, signOut } from "../lib/auth";

type Usage = {
  daily: { day: string; requests: number; testers: number; p95_latency_ms: number | null }[];
  models: { provider: string; model: string; workflow: string; cost_source: string | null;
    llm_calls: number; input_tokens: number | null; output_tokens: number | null;
    unknown_token_calls: number; known_cost_usd: number | null; unknown_cost_calls: number }[];
  feedback: { kind: string; count: number }[];
};

export default function PilotUsage({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [days, setDays] = useState("7");
  const [data, setData] = useState<Usage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/pilot/usage?days=${days}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` }, cache: "no-store"
      });
      if (response.status === 401) { signOut(); return; }
      if (!response.ok) throw new Error(`Pilot report unavailable (${response.status}).`);
      setData(await response.json());
    } catch (error) {
      setError(error instanceof Error ? error.message : "Pilot report unavailable.");
    } finally { setBusy(false); }
  }
  return (
    <section className="mt-7 border-t border-line pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium">Pilot usage</h3>
        <select aria-label="Pilot reporting period" value={days}
          onChange={(event) => { setDays(event.target.value); setData(null); }}
          className="h-8 rounded-md border border-line bg-surface-900 text-xs">
          <option value="7">7 days</option><option value="30">30 days</option><option value="90">90 days</option>
        </select>
        <button type="button" onClick={() => void refresh()} disabled={busy}
          title="Load pilot report" aria-label="Load pilot report"
          className="grid h-8 w-8 place-items-center rounded-md hover:bg-surface-850 disabled:opacity-50">
          <RefreshCw size={15} className={busy ? "animate-spin" : ""} />
        </button>
      </div>
      <p role="status" className="mt-2 text-xs text-muted">{error || (busy ? "Loading..." : "")}</p>
      {data ? <div className="space-y-3 break-words text-xs leading-5 text-muted">
        <p>{data.daily.reduce((total, day) => total + day.requests, 0)} requests</p>
        {data.daily.map((day) => <p key={day.day}>{day.day}: {day.requests} requests, {day.testers} testers,
          p95 {day.p95_latency_ms === null ? "unavailable" : `${Math.round(day.p95_latency_ms)} ms`}</p>)}
        {data.models.map((row, index) => <div key={index} className="border-t border-line pt-2">
          <p className="font-medium text-ink">{row.provider} / {row.model}</p>
          <p>{row.workflow || "Unclassified"} | {row.llm_calls} calls</p>
          <p>Input: {row.input_tokens ?? "unknown"} | Output: {row.output_tokens ?? "unknown"}</p>
          <p>Known cost: {row.known_cost_usd === null ? "unavailable" : `$${Number(row.known_cost_usd).toFixed(6)}`}</p>
          <p>Source: {row.cost_source || "unavailable"}</p>
          <p>Unknown cost: {row.unknown_cost_calls} calls | Unknown tokens: {row.unknown_token_calls} calls</p>
        </div>)}
        {data.feedback.map((row) => <p key={row.kind}>{row.kind.replaceAll("_", " ")}: {row.count}</p>)}
        {!data.daily.length ? <p>No pilot requests in this period.</p> : null}
      </div> : null}
    </section>
  );
}
