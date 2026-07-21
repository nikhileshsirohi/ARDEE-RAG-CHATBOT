"use client";

import { useCallback, useEffect, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ChatWorkspace } from "@/components/ChatWorkspace";
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
      <div className="text-xs font-black uppercase text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-black text-slate-950">{formatNumber(value)}</div>
    </div>
  );
}

function MyUsage({ reloadToken }: { reloadToken: number }) {
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
  }, [load, reloadToken]);

  return (
    <div className="space-y-5">
      <div className="admin-panel p-0">
        <div className="admin-section-head">
          <div>
            <h2 className="text-lg font-black text-slate-950">My token usage</h2>
            <p className="text-sm text-slate-500">Your total consumption across every session.</p>
          </div>
          <button className="btn btn-secondary" onClick={() => void load()} type="button">
            Refresh
          </button>
        </div>
        <div className="p-4">
          {error ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
              {error}
            </div>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <UsageTile label="Total tokens" tone="rose" value={usage?.total_tokens ?? 0} />
            <UsageTile label="Input tokens" tone="blue" value={usage?.input_tokens ?? 0} />
            <UsageTile label="Output tokens" tone="green" value={usage?.output_tokens ?? 0} />
            <UsageTile label="Embedding" tone="gold" value={usage?.embedding_tokens ?? 0} />
            <UsageTile label="Requests" tone="slate" value={usage?.request_count ?? 0} />
          </div>
        </div>
      </div>

      <div className="admin-panel p-0">
        <div className="admin-section-head">
          <div>
            <h2 className="text-lg font-black text-slate-950">Per-session usage</h2>
            <p className="text-sm text-slate-500">
              {usage ? `${usage.session_count} sessions with usage` : "Loading..."}
            </p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Session</th>
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
                    <div className="font-black text-slate-950">{session.title}</div>
                    <div className="text-xs text-slate-500">
                      {formatDate(session.last_message_at)}
                    </div>
                  </td>
                  <td className="font-black">{formatNumber(session.total_tokens)}</td>
                  <td>{formatNumber(session.input_tokens)}</td>
                  <td>{formatNumber(session.output_tokens)}</td>
                  <td>{formatNumber(session.embedding_tokens)}</td>
                  <td>{formatNumber(session.request_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && usage && usage.sessions.length === 0 ? (
            <div className="p-5 text-sm text-slate-500">No usage recorded yet. Ask a question to get started.</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Dashboard({ user }: { user: SessionUser }) {
  const [tab, setTab] = useState<"chat" | "usage">("chat");
  const [usageVersion, setUsageVersion] = useState(0);

  return (
    <div className="app-shell flex h-screen flex-col">
      <AppNav user={user} />
      <main className="mx-auto flex min-h-0 w-full max-w-7xl flex-1 flex-col gap-4 px-4 py-4 lg:px-6">
        <div className="flex items-center gap-2">
          <button
            className={`btn ${tab === "chat" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setTab("chat")}
            type="button"
          >
            Chat
          </button>
          <button
            className={`btn ${tab === "usage" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              setUsageVersion((version) => version + 1);
              setTab("usage");
            }}
            type="button"
          >
            My usage
          </button>
        </div>

        {tab === "chat" ? (
          <ChatWorkspace
            heading="RAG chat"
            subheading="Answers stream live from the LLM and cite the source file and page."
            onActivity={() => setUsageVersion((version) => version + 1)}
          />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto pb-4">
            <MyUsage reloadToken={usageVersion} />
          </div>
        )}
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return <ProtectedRoute>{(user) => <Dashboard user={user} />}</ProtectedRoute>;
}
