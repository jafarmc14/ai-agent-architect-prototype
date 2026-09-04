"use client";

import {
  ChevronRight,
  Loader2,
  LogOut,
  RefreshCw,
  Send,
  ServerCog,
  X
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { getAuthToken, getAuthUser, signOut } from "../lib/auth";

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

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const suggestions = ["Search for a product", "Check an order", "Ask about a policy"];

export default function Home() {
  const [checkedAuth, setCheckedAuth] = useState(false);
  const [currentUser, setCurrentUser] = useState<{ name?: string; email?: string } | null>(null);
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
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const sessionId = useRef(`next-${crypto.randomUUID()}`);

  const isEmptyState = messages.length <= 1 && !isLoading;

  const status = useMemo(() => {
    if (apiError) return { label: "Disconnected", dot: "bg-danger-action" };
    if (isLoading) return { label: "Processing", dot: "bg-warning" };
    return { label: "Ready", dot: "bg-success" };
  }, [apiError, isLoading]);

  useEffect(() => {
    if (!getAuthToken()) {
      window.location.replace("/login");
      return;
    }
    setCurrentUser(getAuthUser());
    setCheckedAuth(true);
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
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const token = getAuthToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await fetch(`${apiBaseUrl}/api/v1/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          message: trimmed,
          session_id: sessionId.current
        })
      });
      if (response.status === 401) {
        signOut();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = (await response.json()) as ChatResponse;
      const assistantText =
        data.response || `Sorry, the API returned an empty response.${data.exception ? ` ${data.exception}` : ""}`;
      setLastResponse(data);
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

  if (!checkedAuth) {
    return null;
  }

  const latency = lastResponse?.request_latency_ms ?? 0;
  const tokens = lastResponse?.token_usage?.total_tokens ?? 0;
  const llmCalls = lastResponse?.token_usage?.llm_calls ?? 0;
  const cost =
    typeof lastResponse?.token_usage?.cost_usd === "number"
      ? `$${lastResponse.token_usage.cost_usd.toFixed(4)}`
      : "$0.0000";

  return (
    <main className="min-h-screen bg-surface-950 text-ink">
      <div className="grid min-h-screen grid-cols-1 xl:grid-cols-[224px_minmax(0,1fr)_auto]">
        <aside className="flex flex-col border-b border-line bg-surface-900 px-4 py-5 xl:border-b-0 xl:border-r">
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-md bg-amber-soft text-sm font-semibold text-amber-action">
              U
            </div>
            <span className="text-lg font-semibold tracking-tight">Ubichinon</span>
          </div>

          <div className="mt-auto space-y-3 pt-8">
            {currentUser?.email ? (
              <div className="flex items-center gap-2.5">
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-850 text-sm font-semibold text-amber-action">
                  {((currentUser.name || currentUser.email)[0] ?? "U").toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">
                    {currentUser.name || currentUser.email}
                  </p>
                  <p className="truncate text-xs text-faint">{currentUser.email}</p>
                </div>
              </div>
            ) : null}
            <button
              className="inline-flex h-9 w-full items-center gap-2 rounded-md px-2.5 text-sm font-medium text-danger-action transition hover:bg-danger-soft"
              type="button"
              onClick={signOut}
            >
              <LogOut size={15} aria-hidden />
              Sign out
            </button>
          </div>
        </aside>

        <section className="grid min-h-screen grid-rows-[auto_minmax(0,1fr)_auto] bg-surface-950">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-ink">Assistant</h2>
              <p className="text-sm text-muted">Store operations</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                className="inline-flex h-8 items-center gap-2 rounded-md border border-line bg-surface-850 px-3 text-xs font-medium text-muted transition hover:text-ink"
                type="button"
                onClick={() => setDetailsOpen((open) => !open)}
                title="Environment & infrastructure"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} aria-hidden />
                {status.label}
              </button>
              <button
                className="inline-flex h-8 items-center rounded-md border border-line bg-surface-850 px-3 text-xs font-medium text-muted transition hover:text-ink"
                type="button"
                onClick={() => setDetailsOpen((open) => !open)}
              >
                Details
              </button>
            </div>
          </header>

          <div className="min-h-0 overflow-y-auto px-5 py-8">
            {isEmptyState ? (
              <div className="mx-auto flex w-full max-w-xl flex-col items-center pt-16 text-center">
                <h3 className="text-2xl font-semibold tracking-tight text-ink">What can I help with?</h3>
                <p className="mt-2 text-sm leading-6 text-muted">
                  Search inventory, check an order, or ask about a store policy.
                </p>
                <div className="mt-9 grid w-full gap-2.5">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => void sendMessage(suggestion)}
                      className="rounded-md border border-line bg-surface-900 px-4 py-3 text-left text-sm text-ink transition hover:border-slate-600 hover:bg-surface-850"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
                {messages.map((message) => (
                  <MessageRow key={message.id} message={message} />
                ))}
                {isLoading ? (
                  <div className="grid gap-1.5">
                    <p className="text-xs font-medium text-faint">Ubichinon</p>
                    <div className="flex items-center gap-2 px-0.5 text-sm text-muted">
                      <Loader2 className="animate-spin" size={15} aria-hidden />
                      Working on it…
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          <div className="border-t border-line bg-surface-900/50 px-5 py-4">
            {apiError ? (
              <p className="mx-auto mb-3 max-w-[760px] text-sm text-danger-action">{apiError}</p>
            ) : null}
            <form
              className="mx-auto flex max-w-[760px] items-end gap-2 rounded-lg border border-line bg-surface-900 px-3 py-2 transition focus-within:border-slate-600"
              onSubmit={onSubmit}
            >
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
                placeholder="Ask about products, orders, customers, or policies"
                rows={1}
                className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent px-1 py-1.5 text-[15px] leading-6 text-ink outline-none placeholder:text-faint"
              />
              <button
                type="submit"
                disabled={!input.trim() || isLoading}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-amber-action text-surface-950 transition hover:bg-amber-hover disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Send message"
                title="Send"
              >
                <Send size={16} aria-hidden />
              </button>
            </form>
          </div>
        </section>

        {detailsOpen ? (
          <aside className="w-full border-t border-line bg-surface-900 px-5 py-5 xl:w-[300px] xl:border-l xl:border-t-0">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-ink">Details</p>
              <button
                className="grid h-7 w-7 place-items-center rounded-md text-muted transition hover:bg-surface-850 hover:text-ink"
                type="button"
                onClick={() => setDetailsOpen(false)}
                aria-label="Close details"
                title="Close"
              >
                <X size={15} aria-hidden />
              </button>
            </div>

            <div className="mt-4 rounded-md border border-line bg-surface-850 px-3 py-2.5 font-mono text-xs leading-6 text-muted">
              {latency} ms · {tokens.toLocaleString()} tokens · {llmCalls} LLM calls · {cost}
            </div>

            <button
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-muted transition hover:text-ink"
              type="button"
              onClick={() => setTraceOpen((open) => !open)}
            >
              View trace
              <ChevronRight size={13} aria-hidden />
            </button>
            {traceOpen ? (
              <dl className="mt-2 grid gap-2 font-mono text-xs text-muted">
                <MetaRow label="Request" value={lastResponse?.request_id ?? "none"} />
                <MetaRow label="Trace" value={lastResponse?.trace_id ?? "none"} />
                <MetaRow label="Intent" value={lastResponse?.intent ?? "none"} />
                <MetaRow label="Workflow" value={lastResponse?.workflow ?? "none"} />
                <MetaRow
                  label="Limit"
                  value={lastResponse?.resource_limit ? JSON.stringify(lastResponse.resource_limit) : "clear"}
                />
              </dl>
            ) : null}

            <section className="mt-7">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-faint">Environment</p>
                <button
                  className="grid h-7 w-7 place-items-center rounded-md text-muted transition hover:bg-surface-850 hover:text-ink"
                  type="button"
                  onClick={refreshConfig}
                  aria-label="Refresh config"
                  title="Refresh"
                >
                  <RefreshCw size={14} aria-hidden />
                </button>
              </div>
              <dl className="mt-3 grid gap-2 text-sm">
                <MetaRow label="API" value={apiBaseUrl} />
                <MetaRow label="Environment" value={config?.environment ?? "unknown"} />
                <MetaRow label="Database" value={config?.database_provider ?? "unknown"} />
                <MetaRow
                  label="Model"
                  value={config?.provider && config?.model ? `${config.provider} / ${config.model}` : "unknown"}
                />
              </dl>
            </section>

            <section className="mt-7 rounded-md border border-line bg-surface-850 p-3">
              <div className="flex items-center gap-2 text-muted">
                <ServerCog size={14} aria-hidden />
                <p className="text-xs font-medium">Runtime</p>
              </div>
              <div className="mt-3 grid gap-3">
                <label className="grid gap-1.5 text-xs text-faint">
                  Provider
                  <select
                    value={selectedProviderLabel}
                    onChange={(event) => void updateProvider(event.target.value)}
                    disabled={isLoading || Object.keys(providerOptions).length === 0}
                    className="h-9 rounded-md border border-line bg-surface-900 px-2.5 text-sm text-ink outline-none"
                  >
                    {Object.keys(providerOptions).map((label) => (
                      <option key={label} value={label}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1.5 text-xs text-faint">
                  Model
                  <select
                    value={selectedModel}
                    onChange={(event) => void updateProvider(selectedProviderLabel, event.target.value)}
                    disabled={isLoading || !selectedProviderLabel}
                    className="h-9 rounded-md border border-line bg-surface-900 px-2.5 text-sm text-ink outline-none"
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
        ) : null}
      </div>
    </main>
  );
}

function MessageRow({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className="grid gap-1.5">
      <p className="text-xs font-medium text-faint">{isUser ? "You" : "Ubichinon"}</p>
      <div
        className={
          isUser
            ? "max-w-[720px] rounded-md bg-surface-850 px-4 py-3 text-[15px] leading-7 text-ink"
            : "max-w-[760px] px-0.5 text-[15px] leading-7 text-ink"
        }
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-faint">{label}</dt>
      <dd className="mt-0.5 break-words leading-5 text-muted">{value}</dd>
    </div>
  );
}