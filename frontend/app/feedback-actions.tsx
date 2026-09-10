"use client";

import { Flag, Headset, ThumbsDown, ThumbsUp, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { getAuthToken, signOut } from "../lib/auth";

const actions = [
  { kind: "thumbs_up", label: "Helpful", Icon: ThumbsUp },
  { kind: "thumbs_down", label: "Not helpful", Icon: ThumbsDown },
  { kind: "wrong_answer", label: "Wrong answer", Icon: TriangleAlert },
  { kind: "report_issue", label: "Report issue", Icon: Flag },
  { kind: "request_human", label: "Request human", Icon: Headset }
];

export default function FeedbackActions({ requestId, apiBaseUrl }: { requestId: string; apiBaseUrl: string }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const pending = useRef(false);

  async function submit(kind: string) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getAuthToken()}` },
        body: JSON.stringify({ request_id: requestId, kind })
      });
      if (response.status === 401) { signOut(); return; }
      if (!response.ok) throw new Error("Feedback could not be saved. Please try again.");
      const data = await response.json();
      setSelected((current) => [...current.filter((item) =>
        kind.startsWith("thumbs_") ? !item.startsWith("thumbs_") : item !== kind), kind]);
      setNotice(data.ticket_number ? `Support ticket ${data.ticket_number} created.` : "Feedback saved.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Feedback could not be saved.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1" aria-label="Answer feedback">
        {actions.map(({ kind, label, Icon }) => (
          <button key={kind} type="button" title={label} aria-label={label}
            aria-pressed={selected.includes(kind)} disabled={busy || selected.includes(kind)}
            onClick={() => void submit(kind)}
            className={`grid h-9 w-9 place-items-center rounded-md transition hover:bg-surface-850 disabled:opacity-60 ${selected.includes(kind) ? "text-brand-action" : "text-muted"}`}>
            <Icon size={16} aria-hidden />
          </button>
        ))}
      </div>
      <p role="status" className="min-h-5 break-words text-xs text-muted">{notice}</p>
    </div>
  );
}
