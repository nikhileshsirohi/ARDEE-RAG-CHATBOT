"use client";

import { useCallback, useEffect, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { api, ApiError } from "@/lib/api";
import type { MyTokenUsageSummary, SessionUser } from "@/lib/types";

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function formatDate(value: string | null) {
  if (!value) {
    return "No activity";
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function UsageTile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`admin-tile admin-tile-${tone}`}>
      <div className="text-[0.7rem] font-semibold uppercase tracking-[0.08em] text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
        {formatNumber(value)}
      </div>
    </div>
  );
}

function UsageView({ user }: { user: SessionUser }) {
  const [usage, setUsage] = useState<MyTokenUsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setUsage(await api.myUsage());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load usage.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="admin-shell">
      <AppNav user={user} />
      <main className="mx-auto max-w-[1200px] space-y-6 px-4 py-6 lg:px-6">
        <div className="animate-rise flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="page-kicker">Account</p>
            <h1 className="page-title">My token usage</h1>
            <p className="page-lede">Your total consumption across every bot and session.</p>
          </div>
          <button className="btn btn-secondary" onClick={() => void load()} type="button">
            Refresh
          </button>
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            {error}
          </div>
        ) : null}

        <div className="animate-rise-delay grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <UsageTile label="Total tokens" tone="rose" value={usage?.total_tokens ?? 0} />
          <UsageTile label="Input tokens" tone="blue" value={usage?.input_tokens ?? 0} />
          <UsageTile label="Output tokens" tone="green" value={usage?.output_tokens ?? 0} />
          <UsageTile label="Embedding" tone="gold" value={usage?.embedding_tokens ?? 0} />
          <UsageTile label="Requests" tone="slate" value={usage?.request_count ?? 0} />
        </div>

        <div className="admin-panel animate-rise-delay p-0">
          <div className="admin-section-head">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-slate-950">
                Per-session usage
              </h2>
              <p className="mt-0.5 text-sm text-slate-500">
                {usage ? `${usage.session_count} sessions with usage` : "Loading..."}
              </p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Session</th>
                  <th>Bot</th>
                  <th>Total</th>
                  <th>Input</th>
                  <th>Output</th>
                  <th>Embedding</th>
                  <th>Requests</th>
                </tr>
              </thead>
              <tbody>
                {usage?.sessions.map((session) => (
                  <tr key={session.session_id}>
                    <td>
                      <div className="font-semibold text-slate-950">{session.title}</div>
                      <div className="mt-0.5 text-xs text-slate-500">
                        {formatDate(session.last_message_at)}
                      </div>
                    </td>
                    <td>
                      <span className="badge">{session.bot_name ?? "Unknown bot"}</span>
                    </td>
                    <td className="font-semibold">{formatNumber(session.total_tokens)}</td>
                    <td>{formatNumber(session.input_tokens)}</td>
                    <td>{formatNumber(session.output_tokens)}</td>
                    <td>{formatNumber(session.embedding_tokens)}</td>
                    <td>{formatNumber(session.request_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && usage && usage.sessions.length === 0 ? (
              <div className="p-5 text-sm text-slate-500">
                No usage recorded yet. Start chatting with a bot to get started.
              </div>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  );
}

export default function UsagePage() {
  return <ProtectedRoute>{(user) => <UsageView user={user} />}</ProtectedRoute>;
}
