"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { UsageChart } from "@/components/UsageChart";
import { api, ApiError } from "@/lib/api";
import type { BotTokenUsageMetric, SessionUser, UserTokenUsageMetric } from "@/lib/types";

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
      <div className="text-[0.7rem] font-semibold uppercase tracking-[0.08em] text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
        {formatNumber(value)}
      </div>
    </div>
  );
}

function AdminConsole({ user }: { user: SessionUser }) {
  const [users, setUsers] = useState<UserTokenUsageMetric[]>([]);
  const [botUsage, setBotUsage] = useState<BotTokenUsageMetric[]>([]);
  const [scope, setScope] = useState("all");
  const [chartVersion, setChartVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadMetrics = useCallback(async () => {
    setError("");
    try {
      const [userRows, botRows] = await Promise.all([api.userTokenUsage(), api.botTokenUsage()]);
      setUsers(sortAdminsFirst(userRows));
      setBotUsage(botRows);
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
      users.reduce(
        (acc, row) => ({
          input: acc.input + row.input_tokens,
          output: acc.output + row.output_tokens,
          embedding: acc.embedding + row.embedding_tokens,
          total: acc.total + row.total_tokens,
          requests: acc.requests + row.request_count,
        }),
        { input: 0, output: 0, embedding: 0, total: 0, requests: 0 },
      ),
    [users],
  );

  const selectedUserId = scope.startsWith("user:") ? scope.slice(5) : undefined;
  const selectedBotId = scope.startsWith("bot:") ? scope.slice(4) : undefined;

  return (
    <div className="admin-shell">
      <AppNav user={user} />
      <main className="mx-auto max-w-[1500px] space-y-5 px-4 py-5 lg:px-6">
        <section className="admin-hero animate-rise">
          <div>
            <p className="page-kicker">Admin Console</p>
            <h1 className="page-title">Operations</h1>
            <p className="page-lede">
              Monitor token usage by user and by bot. Manage bots and their knowledge bases from the{" "}
              <Link
                className="font-semibold text-[var(--primary)] underline-offset-2 hover:underline"
                href="/bots"
              >
                Bots
              </Link>{" "}
              page.
            </p>
          </div>
          <div className="grid gap-2 text-sm font-bold text-slate-600 sm:grid-cols-3">
            <span className="admin-mini-stat">{users.length} users</span>
            <span className="admin-mini-stat">{botUsage.length} bots</span>
            <span className="admin-mini-stat">{formatNumber(totals.total)} tokens</span>
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
                <p className="text-sm text-slate-500">Descending by usage — admins listed first.</p>
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
                  {users.map((row) => (
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
              {!loading && users.length === 0 ? (
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
                onChange={(event) => setScope(event.target.value)}
                value={scope}
              >
                <option value="all">All usage</option>
                <optgroup label="By user">
                  {users.map((row) => (
                    <option key={row.user_id} value={`user:${row.user_id}`}>
                      {row.full_name ?? row.email}
                      {row.role === "ADMIN" ? " (admin)" : ""}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="By bot">
                  {botUsage.map((row) => (
                    <option key={row.bot_id ?? "none"} value={`bot:${row.bot_id}`}>
                      {row.name}
                    </option>
                  ))}
                </optgroup>
              </select>
            </div>
            <UsageChart
              selectedBotId={selectedBotId}
              selectedUserId={selectedUserId}
              version={chartVersion}
            />
          </div>
        </section>

        <section className="admin-panel p-0">
          <div className="admin-section-head">
            <div>
              <h2 className="text-lg font-black text-slate-950">Bots &amp; token usage</h2>
              <p className="text-sm text-slate-500">Token consumption grouped by bot.</p>
            </div>
            <Link className="btn btn-secondary" href="/bots">
              Manage bots
            </Link>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Bot</th>
                  <th>Total</th>
                  <th>Input</th>
                  <th>Output</th>
                  <th>Embedding</th>
                  <th>Requests</th>
                </tr>
              </thead>
              <tbody>
                {botUsage.map((row) => (
                  <tr key={row.bot_id ?? "none"}>
                    <td className="font-black text-slate-950">{row.name}</td>
                    <td className="font-black">{formatNumber(row.total_tokens)}</td>
                    <td>{formatNumber(row.input_tokens)}</td>
                    <td>{formatNumber(row.output_tokens)}</td>
                    <td>{formatNumber(row.embedding_tokens)}</td>
                    <td>{formatNumber(row.request_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && botUsage.length === 0 ? (
              <div className="p-5 text-sm text-slate-500">No bots found.</div>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}

export default function AdminPage() {
  return <ProtectedRoute role="ADMIN">{(user) => <AdminConsole user={user} />}</ProtectedRoute>;
}
