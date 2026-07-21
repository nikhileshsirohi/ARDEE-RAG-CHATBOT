"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { getStoredUser } from "@/lib/auth";

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
      const user = getStoredUser();
      router.replace(user?.role === "ADMIN" ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-4 py-10">
      <section className="panel w-full max-w-md p-6">
        <div className="mb-6">
          <p className="text-sm font-black uppercase tracking-wide text-[#176b87]">Ardee RAG</p>
          <h1 className="mt-2 text-3xl font-black text-slate-950">
            {mode === "login" ? "Sign in" : "Create account"}
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            {mode === "login"
              ? "Access your RAG chat sessions and admin workspace."
              : "Register a workspace account to start asking uploaded PDFs."}
          </p>
        </div>
        <form className="space-y-4" onSubmit={onSubmit}>
          {mode === "register" ? (
            <label className="block text-sm font-bold text-slate-700">
              Full name
              <input
                className="input mt-1"
                onChange={(event) => setFullName(event.target.value)}
                value={fullName}
                autoComplete="name"
              />
            </label>
          ) : null}
          <label className="block text-sm font-bold text-slate-700">
            Email
            <input
              className="input mt-1"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
              autoComplete="email"
            />
          </label>
          <label className="block text-sm font-bold text-slate-700">
            Password
            <input
              className="input mt-1"
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
            {loading ? "Working..." : mode === "login" ? "Sign in" : "Register"}
          </button>
        </form>
        <p className="mt-5 text-center text-sm text-slate-600">
          {mode === "login" ? "Need an account?" : "Already registered?"}{" "}
          <Link className="font-bold text-[#176b87]" href={mode === "login" ? "/register" : "/login"}>
            {mode === "login" ? "Register" : "Sign in"}
          </Link>
        </p>
      </section>
    </main>
  );
}
