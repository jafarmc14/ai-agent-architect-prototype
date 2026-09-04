"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { setAuthSession } from "../../lib/auth";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type LoginResponse = {
  token: string;
  user: { name?: string; email?: string; role?: string };
};

const capabilities = [
  "Search inventory and compare products",
  "Check orders and resolve routine issues",
  "Answer store policy questions"
];

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const user = username.trim();
    if (!user || !password || isLoading) return;

    setIsLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: user, password })
      });

      if (response.ok) {
        const data = (await response.json()) as LoginResponse;
        setAuthSession(data.token, data.user);
        router.replace("/");
        return;
      }

      if (response.status === 429) {
        const retryAfter = response.headers.get("Retry-After");
        setError(
          retryAfter
            ? `Too many login attempts. Try again in ${retryAfter} second(s).`
            : "Too many login attempts. Try again later."
        );
      } else if (response.status === 503) {
        setError("Login is currently unavailable. Please try again later.");
      } else {
        setError("Invalid email or password.");
      }
    } catch {
      setError(`Unable to reach API at ${apiBaseUrl}.`);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-surface-950 text-ink">
      <div className="mx-auto grid min-h-screen w-full max-w-6xl grid-cols-1 items-center gap-14 px-6 py-16 md:grid-cols-[1.2fr_minmax(0,400px)] md:gap-20">
        <section>
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-amber-soft text-base font-semibold text-amber-action">
              U
            </div>
            <span className="text-xl font-semibold tracking-tight">Ubichinon</span>
          </div>

          <h1 className="mt-12 max-w-md text-4xl font-semibold leading-tight tracking-tight text-ink">
            Store operations, without the busywork.
          </h1>
          <p className="mt-4 max-w-md text-[15px] leading-7 text-muted">
            Search products, answer policy questions, and handle routine store tasks from one place.
          </p>

          <ul className="mt-10 max-w-md space-y-3">
            {capabilities.map((capability) => (
              <li key={capability} className="flex items-center gap-3 text-sm text-muted">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-action" aria-hidden />
                {capability}
              </li>
            ))}
          </ul>
        </section>

        <section className="w-full">
          <h2 className="text-2xl font-semibold tracking-tight text-ink">Welcome back</h2>
          <p className="mt-1.5 text-sm text-muted">Sign in to Ubichinon</p>

          <form className="mt-9 grid gap-5" onSubmit={onSubmit}>
            <label className="grid gap-1.5 text-sm font-medium text-ink">
              Email
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="you@example.com"
                className="h-11 rounded-md border border-line bg-surface-900 px-3.5 text-[15px] text-ink outline-none placeholder:text-faint focus:border-amber-action"
              />
            </label>

            <label className="grid gap-1.5 text-sm font-medium text-ink">
              Password
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                className="h-11 rounded-md border border-line bg-surface-900 px-3.5 text-[15px] text-ink outline-none placeholder:text-faint focus:border-amber-action"
              />
            </label>

            {error ? (
              <div className="rounded-md border border-danger-soft bg-danger-soft/40 px-3.5 py-2.5 text-sm text-[#e8a29b]">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={!username.trim() || !password || isLoading}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-amber-action text-sm font-semibold text-surface-950 transition hover:bg-amber-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? <Loader2 className="animate-spin" size={16} aria-hidden /> : null}
              {isLoading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <p className="mt-7 text-xs leading-5 text-faint">
            Repeated failed sign-in attempts are temporarily blocked.
          </p>
        </section>
      </div>
    </main>
  );
}