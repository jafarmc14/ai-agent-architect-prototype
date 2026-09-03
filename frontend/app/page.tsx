"use client";

import {
  AlertTriangle,
  Bot,
  Check,
  CircleDollarSign,
  Clock3,
  Database,
  Gauge,
  GitBranch,
  Loader2,
  MessageSquareText,
  RefreshCw,
  Send,
  ServerCog,
  ShieldCheck,
  TerminalSquare,
  UserRound
} from "lucide-react";
import type { ReactNode } from "react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type ChatRole = "assistant" | "user";

type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

type ApiConfig = {
  environment?: string;
  database_provider?: string;
  provider?: string;
  model?: string;
  model_version?: string;
};

type ProviderOption = {
  provider: string;
  models: string[];
};

type ProviderOptionsResponse = {
  options: Record<string, ProviderOption>;
};

type TokenUsage = {
  llm_calls?: number;
  total_tokens?: number;
  input_tokens?: number;
  output_tokens?: number;
  request_latency_ms?: number;
  cost_usd?: number | null;
  workflow?: string | null;
};

type ChatResponse = {
  response?: string;
  request_id?: string;
  trace_id?: string;
  intent?: string | null;
  workflow?: string | null;
  request_latency_ms?: number | null;
  token_usage?: TokenUsage | null;
  resource_usage?: Record<string, unknown> | null;
  resource_limit?: Record<string, unknown> | null;
  exception?: string | null;
};

const quickPrompts = [
  "Find shoes under Rp 1,500,000",
  "What is the return policy?",
  "Add 2 Nike shoes to my cart",
  "I was charged twice, this is a payment dispute."
];

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Hello, I'm Ubichinon. How can I help you today?"
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const [config, setConfig] = useState<ApiConfig | null>(null);
  const [providerOptions, setProviderOptions] = useState<Record<string, ProviderOption>>({});
  const [selectedProviderLabel, setSelectedProviderLabel] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [apiError, setApiError] = useState("");
  const sessionId = useRef(`next-${crypto.randomUUID()}`);

  const status = useMemo(() => {
    if (apiError) return { label: "Disconnected", tone: "danger" };
    if (isLoading) return { label: "Processing", tone: "working" };
    return { label: "Ready", tone: "ok" };
  }, [apiError, isLoading]);

  useEffect(() => {
    void refreshConfig();
  }, []);

  async function refreshConfig() {
    try {
      const [configResponse, providersResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/v1/config`, { cache: "no-store" }),
        fetch(`${apiBaseUrl}/api/v1/providers`, { cache: "no-store" })
      ]);
      if (!configResponse.ok) throw new Error(`Config HTTP ${configResponse.status}`);
      if (!providersResponse.ok) throw new Error(`Providers HTTP ${providersResponse.status}`);
      const nextConfig = (await configResponse.json()) as ApiConfig;
      const nextProviders = (await providersResponse.json()) as ProviderOptionsResponse;
      setConfig(nextConfig);
      setProviderOptions(nextProviders.options);
      syncProviderSelection(nextConfig, nextProviders.options);
      setApiError("");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Unable to reach API");
    }
  }

  function syncProviderSelection(nextConfig: ApiConfig, options: Record<string, ProviderOption>) {
    const match = Object.entries(options).find(([, option]) => option.provider === nextConfig.provider);
    const label = match?.[0] ?? Object.keys(options)[0] ?? "";
    const models = label ? options[label]?.models ?? [] : [];
    setSelectedProviderLabel(label);
    setSelectedModel(nextConfig.model && models.includes(nextConfig.model) ? nextConfig.model : models[0] ?? "");
  }

  async function updateProvider(label: string, modelOverride?: string) {
    const option = providerOptions[label];
    if (!option) return;
    const model = modelOverride ?? option.models[0] ?? "";
    setSelectedProviderLabel(label);
    setSelectedModel(model);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/config/llm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: option.provider, model })
      });
      if (!response.ok) throw new Error(`Provider update HTTP ${response.status}`);
      const nextConfig = (await response.json()) as ApiConfig;
      setConfig(nextConfig);
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content: "Hello, I'm Ubichinon. How can I help you today?"
        }
      ]);
      setLastResponse(null);
      setApiError("");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Unable to update provider");
    } finally {
      setIsLoading(false);
    }
  }

  async function sendMessage(messageText: string) {
    const trimmed = messageText.trim();
    if (!trimmed || isLoading) return;

    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", content: trimmed }
    ]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          session_id: sessionId.current
        })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = (await response.json()) as ChatResponse;
      const assistantText =
        data.response || `Sorry, the API returned an empty response.${data.exception ? ` ${data.exception}` : ""}`;
      setLastResponse(data);
      setConfig((current) => current ?? {});
      setApiError("");
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", content: assistantText }
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to reach API";
      setApiError(message);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `The API is not reachable at ${apiBaseUrl}. Start FastAPI, then try again.`
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage(input);
  }

  return (
    <main className="min-h-screen bg-surface-950 text-ink">
      <div className="grid min-h-screen grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
        <aside className="border-b border-line bg-surface-900 px-5 py-5 xl:border-b-0 xl:border-r">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-amber-action text-surface-950">
              <Bot size={18} aria-hidden />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Store Ops</p>
              <h1 className="truncate text-xl font-semibold tracking-normal">Ubichinon</h1>
            </div>
          </div>

          <section className="mt-6 rounded-lg border border-line bg-surface-850 p-3">
            <div className="flex items-center justify-between gap-3">
              <StatusPill tone={status.tone}>{status.label}</StatusPill>
              <button
                className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-surface-900 text-muted transition hover:border-slate-500 hover:text-ink"
                type="button"
                onClick={refreshConfig}
                aria-label="Refresh config"
                title="Refresh config"
              >
                <RefreshCw size={16} aria-hidden />
              </button>
            </div>
            {apiError ? (
              <div className="mt-3 rounded-lg border border-red-900/80 bg-danger-soft px-3 py-2 text-sm text-red-100">
                {apiError}
              </div>
            ) : null}
          </section>

          <dl className="mt-6 space-y-4 text-sm">
            <MetaRow label="API" value={apiBaseUrl} />
            <MetaRow label="Environment" value={config?.environment ?? "unknown"} />
            <MetaRow label="Database" value={config?.database_provider ?? "unknown"} />
            <MetaRow
              label="Provider"
              value={config?.provider && config?.model ? `${config.provider} / ${config.model}` : "unknown"}
            />
          </dl>

          <section className="mt-6 rounded-lg border border-line bg-surface-850 p-3">
            <div className="flex items-center gap-2 text-muted">
              <ServerCog size={16} aria-hidden />
              <p className="text-[11px] font-bold uppercase tracking-[0.14em]">Provider</p>
            </div>
            <div className="mt-3 grid gap-3">
              <label className="grid gap-1 text-xs font-bold text-muted">
                Runtime
                <select
                  value={selectedProviderLabel}
                  onChange={(event) => void updateProvider(event.target.value)}
                  disabled={isLoading || Object.keys(providerOptions).length === 0}
                  className="h-10 rounded-lg border border-line bg-surface-900 px-3 text-sm font-semibold text-ink outline-none"
                >
                  {Object.keys(providerOptions).map((label) => (
                    <option key={label} value={label}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-xs font-bold text-muted">
                Model
                <select
                  value={selectedModel}
                  onChange={(event) => void updateProvider(selectedProviderLabel, event.target.value)}
                  disabled={isLoading || !selectedProviderLabel}
                  className="h-10 rounded-lg border border-line bg-surface-900 px-3 text-sm font-semibold text-ink outline-none"
                >
                  {(providerOptions[selectedProviderLabel]?.models ?? []).map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>
        </aside>

        <section className="grid min-h-screen grid-rows-[auto_minmax(0,1fr)_auto] bg-surface-950">
          <header className="border-b border-line px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Development client</p>
                <h2 className="mt-1 text-2xl font-semibold tracking-normal">Agent workspace</h2>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <HeaderBadge icon={<TerminalSquare size={14} />} label="FastAPI" />
                <HeaderBadge icon={<GitBranch size={14} />} label={config?.model_version ?? "alias"} />
              </div>
            </div>
          </header>

          <div className="min-h-0 overflow-y-auto px-5 py-5">
            <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
              {messages.map((message) => (
                <ChatBubble key={message.id} message={message} />
              ))}
              {isLoading ? (
                <div className="flex items-start gap-3">
                  <Avatar role="assistant">
                    <Loader2 className="animate-spin" size={17} />
                  </Avatar>
                  <div className="rounded-lg border border-line bg-surface-850 px-4 py-3 text-sm text-muted">
                    Working on it...
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div className="border-t border-line bg-surface-900/70 px-5 py-4">
            <form className="mx-auto flex max-w-4xl items-end gap-3" onSubmit={onSubmit}>
              <label htmlFor="messageInput" className="sr-only">
                Message
              </label>
              <textarea
                id="messageInput"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendMessage(input);
                  }
                }}
                placeholder="Ask about products, orders, policies, carts, or support..."
                rows={2}
                className="min-h-[52px] flex-1 resize-y rounded-lg border border-line bg-surface-800 px-4 py-3 text-[15px] leading-6 text-ink outline-none placeholder:text-slate-500"
              />
              <button
                type="submit"
                disabled={!input.trim() || isLoading}
                className="grid h-[52px] w-[52px] place-items-center rounded-lg bg-amber-action text-surface-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Send message"
                title="Send"
              >
                <Send size={18} aria-hidden />
              </button>
            </form>
          </div>
        </section>

        <aside className="border-t border-line bg-surface-900 px-5 py-5 xl:border-l xl:border-t-0">
          <section>
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Command Queue</p>
              <MessageSquareText size={16} className="text-muted" aria-hidden />
            </div>
            <div className="mt-3 grid gap-2">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => void sendMessage(prompt)}
                  disabled={isLoading}
                  className="rounded-lg border border-line bg-surface-850 px-3 py-2 text-left text-sm leading-5 text-ink transition hover:border-slate-500 hover:bg-surface-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </section>

          <section className="mt-6">
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Last Request</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Metric icon={<Clock3 size={15} />} label="Latency" value={`${lastResponse?.request_latency_ms ?? 0} ms`} />
              <Metric icon={<Database size={15} />} label="Tokens" value={`${lastResponse?.token_usage?.total_tokens ?? 0}`} />
              <Metric icon={<ShieldCheck size={15} />} label="Workflow" value={lastResponse?.workflow ?? "none"} />
              <Metric icon={<Gauge size={15} />} label="LLM calls" value={`${lastResponse?.token_usage?.llm_calls ?? 0}`} />
              <Metric
                icon={<CircleDollarSign size={15} />}
                label="Cost"
                value={
                  typeof lastResponse?.token_usage?.cost_usd === "number"
                    ? `$${lastResponse.token_usage.cost_usd.toFixed(6)}`
                    : "$0.000000"
                }
              />
              <Metric icon={<Check size={15} />} label="Intent" value={lastResponse?.intent ?? "none"} />
            </div>
          </section>

          <section className="mt-6 rounded-lg border border-line bg-surface-850 p-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Trace</p>
            <dl className="mt-3 space-y-3 text-sm">
              <MetaRow label="Request" value={lastResponse?.request_id ?? "none"} />
              <MetaRow label="Trace" value={lastResponse?.trace_id ?? "none"} />
              <MetaRow
                label="Limit"
                value={lastResponse?.resource_limit ? JSON.stringify(lastResponse.resource_limit) : "clear"}
              />
            </dl>
          </section>
        </aside>
      </div>
    </main>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <article className={`flex items-start gap-3 ${isUser ? "justify-end" : ""}`}>
      {!isUser ? (
        <Avatar role="assistant">
          <Bot size={17} />
        </Avatar>
      ) : null}
      <div
        className={`max-w-[760px] rounded-lg border px-4 py-3 text-[15px] leading-7 shadow-panel ${
          isUser
            ? "border-slate-700 bg-surface-750 text-ink"
            : "border-line bg-surface-850 text-ink"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
      {isUser ? (
        <Avatar role="user">
          <UserRound size={17} />
        </Avatar>
      ) : null}
    </article>
  );
}

function Avatar({ role, children }: { role: ChatRole; children: ReactNode }) {
  return (
    <div
      className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${
        role === "assistant" ? "bg-amber-action text-surface-950" : "bg-danger-action text-surface-950"
      }`}
      aria-hidden
    >
      {children}
    </div>
  );
}

function Metric({
  icon,
  label,
  value
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-line bg-surface-850 p-3">
      <div className="flex items-center gap-2 text-muted">
        {icon}
        <span className="truncate text-xs font-bold">{label}</span>
      </div>
      <strong className="mt-2 block truncate text-sm font-semibold text-ink">{value}</strong>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-bold text-muted">{label}</dt>
      <dd className="mt-1 break-words text-sm leading-5 text-ink">{value}</dd>
    </div>
  );
}

function HeaderBadge({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <span className="inline-flex h-8 max-w-[260px] items-center gap-2 rounded-lg border border-line bg-surface-850 px-3 text-xs font-semibold text-muted">
      {icon}
      <span className="truncate">{label}</span>
    </span>
  );
}

function StatusPill({ tone, children }: { tone: string; children: ReactNode }) {
  const dot =
    tone === "danger" ? "bg-red-400" : tone === "working" ? "bg-yellow-300" : "bg-emerald-400";
  return (
    <span className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
      <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
      {children}
    </span>
  );
}
