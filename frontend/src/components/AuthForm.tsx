"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, ApiError } from "@/lib/api";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "register") {
        await api.register({ email, password, full_name: fullName || undefined });
      }
      await api.login({ email, password });
      router.replace("/bots");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="mb-7">
          <p className="brand-mark text-2xl text-[var(--foreground)]">
            Ardee<span className="text-[var(--primary)]">.</span>
          </p>
          <h1 className="page-title mt-5">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="page-lede">
            {mode === "login"
              ? "Sign in to your RAG workspace and pick up where you left off."
              : "Register to chat with uploaded PDFs — answers grounded in your documents."}
          </p>
        </div>
        <form className="space-y-4" onSubmit={onSubmit}>
          {mode === "register" ? (
            <label className="block text-sm font-semibold text-slate-700">
              Full name
              <input
                className="input mt-1.5"
                onChange={(event) => setFullName(event.target.value)}
                value={fullName}
                autoComplete="name"
              />
            </label>
          ) : null}
          <label className="block text-sm font-semibold text-slate-700">
            Email
            <input
              className="input mt-1.5"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
              autoComplete="email"
            />
          </label>
          <label className="block text-sm font-semibold text-slate-700">
            Password
            <input
              className="input mt-1.5"
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {error ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
              {error}
            </div>
          ) : null}
          <button className="btn btn-primary w-full" disabled={loading} type="submit">
            {loading ? "Working..." : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-600">
          {mode === "login" ? "Need an account?" : "Already registered?"}{" "}
          <Link
            className="font-semibold text-[var(--primary)] underline-offset-2 hover:underline"
            href={mode === "login" ? "/register" : "/login"}
          >
            {mode === "login" ? "Register" : "Sign in"}
          </Link>
        </p>
      </section>
    </main>
  );
}
