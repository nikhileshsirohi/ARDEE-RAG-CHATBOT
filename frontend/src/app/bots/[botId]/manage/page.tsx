"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { api, ApiError } from "@/lib/api";
import type { Bot, SessionUser } from "@/lib/types";

const PROMPT_PLACEHOLDER =
  "e.g. You are the ACME HR assistant. Answer employee questions about company " +
  "policies using only the attached handbook. Be friendly and concise.";

function ManageBot({ user, botId }: { user: SessionUser; botId: string }) {
  const router = useRouter();
  const [bot, setBot] = useState<Bot | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await api.bot(botId);
      setBot(next);
      setName(next.name);
      setDescription(next.description ?? "");
      setSystemPrompt(next.system_prompt);
      setIsActive(next.is_active);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load this bot.");
    }
  }, [botId]);

  useEffect(() => {
    void load();
  }, [load]);

  const dirty =
    bot !== null &&
    (name.trim() !== bot.name ||
      (description.trim() || "") !== (bot.description ?? "") ||
      systemPrompt.trim() !== bot.system_prompt ||
      isActive !== bot.is_active);

  async function onSave(event: FormEvent) {
    event.preventDefault();
    if (!bot) {
      return;
    }
    const trimmedName = name.trim();
    const trimmedPrompt = systemPrompt.trim();
    if (!trimmedName) {
      setError("A bot name is required.");
      return;
    }
    if (!trimmedPrompt) {
      setError("A prompt is required so the bot knows how to behave.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const saved = await api.updateBot(bot.id, {
        name: trimmedName,
        description: description.trim(),
        system_prompt: trimmedPrompt,
        is_active: isActive,
      });
      setBot(saved);
      setName(saved.name);
      setDescription(saved.description ?? "");
      setSystemPrompt(saved.system_prompt);
      setIsActive(saved.is_active);
      setNotice("Changes saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save the bot.");
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!bot) {
      return;
    }
    setDeleteBusy(true);
    setError("");
    try {
      await api.deleteBot(bot.id);
      router.replace("/bots");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed.");
      setPendingDelete(false);
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="admin-shell">
      <AppNav user={user} />
      <main className="mx-auto max-w-[1100px] space-y-6 px-4 py-6 lg:px-6">
        <div className="animate-rise flex flex-wrap items-end justify-between gap-3">
          <div>
            <Link
              className="text-xs font-semibold text-[var(--primary)] underline-offset-2 hover:underline"
              href="/bots"
            >
              ← All bots
            </Link>
            <p className="page-kicker mt-3">Bot settings</p>
            <h1 className="page-title">{bot?.name ?? "Loading..."}</h1>
            <p className="page-lede">
              Edit details inline, then save. Attach PDFs below for grounded answers.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {bot?.is_active ? (
              <Link className="btn btn-secondary" href={`/bots/${bot.id}`}>
                Open chat
              </Link>
            ) : bot ? (
              <button className="btn btn-secondary" disabled type="button">
                Open chat
              </button>
            ) : null}
            <button
              className="btn btn-danger"
              disabled={!bot || deleteBusy}
              onClick={() => setPendingDelete(true)}
              type="button"
            >
              Delete bot
            </button>
          </div>
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            {error}
          </div>
        ) : null}
        {notice ? (
          <div className="rounded-lg border border-[var(--primary-soft-border)] bg-[var(--accent-soft)] px-3 py-2 text-sm font-semibold text-[var(--accent)]">
            {notice}
          </div>
        ) : null}

        <section className="admin-panel animate-rise-delay overflow-hidden p-0">
          <form onSubmit={onSave}>
            <div className="border-b border-[var(--line)] px-5 py-4">
              <h2 className="text-base font-semibold tracking-tight text-slate-950">Details</h2>
              <p className="mt-0.5 text-sm text-slate-500">Name, description, prompt, and status.</p>
            </div>

            <div className="grid gap-5 p-5 lg:grid-cols-2">
              <label className="block text-sm font-semibold text-slate-700 lg:col-span-1">
                Name
                <input
                  className="input mt-1.5"
                  disabled={!bot}
                  onChange={(event) => {
                    setName(event.target.value);
                    setNotice("");
                  }}
                  placeholder="e.g. HR Policy Assistant"
                  value={name}
                />
              </label>

              <label className="flex items-end gap-3 text-sm font-semibold text-slate-700">
                <span className="flex-1">
                  Status
                  <span className="mt-1.5 flex items-center gap-3 rounded-[var(--radius-sm)] border border-[var(--line-strong)] bg-white px-3 py-2.5 shadow-[var(--shadow-sm)]">
                    <input
                      checked={isActive}
                      className="h-4 w-4 accent-[var(--primary)]"
                      disabled={!bot}
                      onChange={(event) => {
                        setIsActive(event.target.checked);
                        setNotice("");
                      }}
                      type="checkbox"
                    />
                    <span className="font-medium text-slate-700">
                      {isActive ? "Active — available for chat" : "Inactive — hidden from chat"}
                    </span>
                  </span>
                </span>
              </label>

              <label className="block text-sm font-semibold text-slate-700 lg:col-span-2">
                Description <span className="font-medium text-slate-400">(optional)</span>
                <input
                  className="input mt-1.5"
                  disabled={!bot}
                  onChange={(event) => {
                    setDescription(event.target.value);
                    setNotice("");
                  }}
                  placeholder="Short summary shown on the bot card"
                  value={description}
                />
              </label>

              <label className="block text-sm font-semibold text-slate-700 lg:col-span-2">
                Prompt
                <textarea
                  className="input mt-1.5 min-h-40 resize-y leading-6"
                  disabled={!bot}
                  onChange={(event) => {
                    setSystemPrompt(event.target.value);
                    setNotice("");
                  }}
                  placeholder={PROMPT_PLACEHOLDER}
                  value={systemPrompt}
                />
              </label>
            </div>

            <div className="flex items-center justify-between gap-3 border-t border-[var(--line)] bg-[var(--surface-subtle)]/70 px-5 py-3">
              <p className="text-xs font-medium text-slate-500">
                {dirty ? "You have unsaved changes." : bot ? "All changes saved." : "Loading bot..."}
              </p>
              <button className="btn btn-primary" disabled={!bot || saving || !dirty} type="submit">
                {saving ? "Saving..." : "Save changes"}
              </button>
            </div>
          </form>
        </section>

        <div className="animate-rise-delay">
          <DocumentsPanel botId={botId} onActivity={() => void load()} />
        </div>
      </main>

      <ConfirmDialog
        busy={deleteBusy}
        confirmLabel="Delete bot"
        message={
          <>
            Delete <span className="font-semibold text-slate-800">{bot?.name}</span>? Its chat
            sessions and knowledge base will no longer be accessible. This cannot be undone.
          </>
        }
        onCancel={() => setPendingDelete(false)}
        onConfirm={() => void confirmDelete()}
        open={pendingDelete}
        title="Delete bot"
        tone="danger"
      />
    </div>
  );
}

export default function ManageBotPage() {
  const params = useParams<{ botId: string }>();
  const botId = params?.botId;
  return (
    <ProtectedRoute role="ADMIN">
      {(user) =>
        botId ? (
          <ManageBot botId={botId} user={user} />
        ) : (
          <main className="grid min-h-screen place-items-center px-4">
            <div className="panel px-5 py-4 text-sm font-semibold text-slate-600">
              Bot not found.
            </div>
          </main>
        )
      }
    </ProtectedRoute>
  );
}
