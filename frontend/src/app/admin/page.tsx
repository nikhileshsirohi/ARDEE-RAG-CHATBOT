"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { ChatWorkspace } from "@/components/ChatWorkspace";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { UsageChart } from "@/components/UsageChart";
import { api, ApiError } from "@/lib/api";
import type { SessionUser, UserTokenUsageMetric } from "@/lib/types";

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

/** Admins first (descending), then everyone else descending by total tokens. */
function sortAdminsFirst(rows: UserTokenUsageMetric[]) {
  return [...rows].sort((a, b) => {
    if (a.role !== b.role) {
      return a.role === "ADMIN" ? -1 : 1;
    }
    return b.total_tokens - a.total_tokens;
  });
}

function MetricTile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`admin-tile admin-tile-${tone}`}>
      <div className="text-xs font-black uppercase text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-black text-slate-950">{formatNumber(value)}</div>
    </div>
  );
}

function AdminConsole({ user }: { user: SessionUser }) {
  const [metrics, setMetrics] = useState<UserTokenUsageMetric[]>([]);
  const [selectedUserId, setSelectedUserId] = useState("all");
  const [chartVersion, setChartVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadMetrics = useCallback(async () => {
    setError("");
    try {
      const rows = await api.userTokenUsage();
      setMetrics(sortAdminsFirst(rows));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load metrics.");
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await loadMetrics();
    setChartVersion((version) => version + 1);
  }, [loadMetrics]);

  useEffect(() => {
    async function boot() {
      try {
        await loadMetrics();
      } finally {
        setLoading(false);
      }
    }
    void boot();
  }, [loadMetrics]);

  const totals = useMemo(
    () =>
      metrics.reduce(
        (acc, row) => ({
          input: acc.input + row.input_tokens,
          output: acc.output + row.output_tokens,
          embedding: acc.embedding + row.embedding_tokens,
          total: acc.total + row.total_tokens,
          requests: acc.requests + row.request_count,
        }),
        { input: 0, output: 0, embedding: 0, total: 0, requests: 0 },
      ),
    [metrics],
  );

  return (
    <div className="admin-shell">
      <AppNav user={user} />
      <main className="mx-auto max-w-[1500px] space-y-5 px-4 py-5 lg:px-6">
        <section className="admin-hero">
          <div>
            <p className="text-xs font-black uppercase tracking-wide text-[#46615a]">Admin Console</p>
            <h1 className="mt-2 text-3xl font-black text-slate-950">RAG operations dashboard</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              Manage the document library, monitor per-user token usage, and test the streaming RAG
              chatbot — all from one admin session.
            </p>
          </div>
          <div className="grid gap-2 text-sm font-bold text-slate-600 sm:grid-cols-3">
            <span className="admin-mini-stat">{metrics.length} users</span>
            <span className="admin-mini-stat">{formatNumber(totals.total)} tokens</span>
            <span className="admin-mini-stat">{formatNumber(totals.requests)} requests</span>
          </div>
        </section>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            {error}
          </div>
        ) : null}

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <MetricTile label="Total tokens" tone="rose" value={totals.total} />
          <MetricTile label="Input tokens" tone="blue" value={totals.input} />
          <MetricTile label="Output tokens" tone="green" value={totals.output} />
          <MetricTile label="Embedding tokens" tone="gold" value={totals.embedding} />
          <MetricTile label="Requests" tone="slate" value={totals.requests} />
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="admin-panel p-0">
            <div className="admin-section-head">
              <div>
                <h2 className="text-lg font-black text-slate-950">Users &amp; token usage</h2>
                <p className="text-sm text-slate-500">
                  Descending by usage — admins listed first.
                </p>
              </div>
              <button className="btn btn-secondary" onClick={() => void refreshAll()} type="button">
                Refresh
              </button>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Role</th>
                    <th>Total</th>
                    <th>Input</th>
                    <th>Output</th>
                    <th>Embedding</th>
                    <th>Requests</th>
                  </tr>
                </thead>
                <tbody>
                  {metrics.map((row) => (
                    <tr key={row.user_id}>
                      <td>
                        <div className="font-black text-slate-950">
                          {row.full_name ?? "Unnamed user"}
                        </div>
                        <div className="text-xs text-slate-500">{row.email}</div>
                      </td>
                      <td>
                        <span className={`badge ${row.role === "ADMIN" ? "role-admin" : ""}`}>
                          {row.role}
                        </span>
                      </td>
                      <td className="font-black">{formatNumber(row.total_tokens)}</td>
                      <td>{formatNumber(row.input_tokens)}</td>
                      <td>{formatNumber(row.output_tokens)}</td>
                      <td>{formatNumber(row.embedding_tokens)}</td>
                      <td>{formatNumber(row.request_count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!loading && metrics.length === 0 ? (
                <div className="p-5 text-sm text-slate-500">No users found.</div>
              ) : null}
            </div>
          </div>

          <div className="admin-panel p-5">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-black text-slate-950">Daily token usage</h2>
                <p className="text-sm text-slate-500">Tokens per day (in 1K) for a selected week.</p>
              </div>
              <select
                className="input sm:max-w-56"
                onChange={(event) => setSelectedUserId(event.target.value)}
                value={selectedUserId}
              >
                <option value="all">All users</option>
                {metrics.map((row) => (
                  <option key={row.user_id} value={row.user_id}>
                    {row.full_name ?? row.email}
                    {row.role === "ADMIN" ? " (admin)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <UsageChart selectedUserId={selectedUserId} version={chartVersion} />
          </div>
        </section>

        <DocumentsPanel onActivity={() => void refreshAll()} />

        <section className="admin-panel flex h-[720px] flex-col overflow-hidden p-0">
          <div className="admin-section-head">
            <div>
              <h2 className="text-lg font-black text-slate-950">Admin chatbot</h2>
              <p className="text-sm text-slate-500">
                Streaming answers with citations, across your own admin sessions.
              </p>
            </div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col p-4">
            <ChatWorkspace
              heading="Admin RAG chat"
              subheading="Live-streamed answers grounded in the uploaded PDFs."
              onActivity={() => void refreshAll()}
            />
          </div>
        </section>
      </main>
    </div>
  );
}

export default function AdminPage() {
  return <ProtectedRoute role="ADMIN">{(user) => <AdminConsole user={user} />}</ProtectedRoute>;
}
