"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { BotFormModal } from "@/components/BotFormModal";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { api, ApiError } from "@/lib/api";
import type { Bot, SessionUser } from "@/lib/types";

function initials(name: string) {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "B";
}

function BotCard({ bot, isAdmin }: { bot: Bot; isAdmin: boolean }) {
  const detailHref = isAdmin ? `/bots/${bot.id}/manage` : `/bots/${bot.id}`;
  const canOpenBot = isAdmin || bot.is_active;
  const canChat = bot.is_active;
  const cardContent = (
    <>
      <div className="flex items-start gap-3">
        <span aria-hidden className="bot-avatar">
          {initials(bot.name)}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-semibold tracking-tight text-slate-950 transition group-hover:text-[var(--primary-strong)]">
            {bot.name}
          </h3>
          <p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-500">
            {bot.description || "No description provided."}
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span className="badge">
          {bot.ready_document_count}/{bot.document_count} docs ready
        </span>
        {!bot.is_active ? <span className="badge role-admin">Inactive</span> : null}
        {isAdmin ? (
          <span className="text-xs font-medium text-slate-400 opacity-0 transition group-hover:opacity-100">
            Open settings →
          </span>
        ) : null}
      </div>
    </>
  );

  return (
    <article className="bot-card group">
      {canOpenBot ? (
        <Link className="flex min-w-0 flex-1 flex-col outline-none" href={detailHref}>
          {cardContent}
        </Link>
      ) : (
        <div aria-disabled="true" className="flex min-w-0 flex-1 flex-col opacity-75">
          {cardContent}
        </div>
      )}

      <div className="mt-auto flex pt-5">
        {canChat ? (
          <Link
            className="btn btn-primary w-full"
            href={`/bots/${bot.id}`}
            onClick={(event) => event.stopPropagation()}
          >
            Chat
          </Link>
        ) : (
          <button className="btn btn-primary w-full" disabled type="button">
            Chat
          </button>
        )}
      </div>
    </article>
  );
}

function BotsLanding({ user }: { user: SessionUser }) {
  const router = useRouter();
  const isAdmin = user.role === "ADMIN";
  const [bots, setBots] = useState<Bot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      setBots(await api.bots());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load bots.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="app-shell flex min-h-screen flex-col">
      <AppNav user={user} />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 lg:px-6">
        <div className="animate-rise flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="page-kicker">Your workspace</p>
            <h1 className="page-title">Bots</h1>
            <p className="page-lede">
              {isAdmin
                ? "Create bots, open one to edit its prompt and documents, or jump straight into chat."
                : "Pick a bot to start a grounded, cited conversation with its documents."}
            </p>
          </div>
          {isAdmin ? (
            <button className="btn btn-primary" onClick={() => setCreateOpen(true)} type="button">
              + Create bot
            </button>
          ) : null}
        </div>

        {error ? (
          <div className="mt-5 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="mt-10 text-sm text-slate-500">Loading bots...</div>
        ) : bots.length === 0 ? (
          <div className="animate-rise-delay mt-10 rounded-xl border border-dashed border-[var(--line-strong)] bg-white/50 p-12 text-center backdrop-blur-sm">
            <h2 className="text-lg font-semibold tracking-tight text-slate-800">No bots yet</h2>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              {isAdmin
                ? "Create your first bot, give it a prompt, and attach the PDFs it should answer from."
                : "No bots have been created yet. Please check back later."}
            </p>
            {isAdmin ? (
              <button
                className="btn btn-primary mt-5"
                onClick={() => setCreateOpen(true)}
                type="button"
              >
                + Create bot
              </button>
            ) : null}
          </div>
        ) : (
          <div className="animate-rise-delay mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {bots.map((bot) => (
              <BotCard bot={bot} isAdmin={isAdmin} key={bot.id} />
            ))}
          </div>
        )}
      </main>

      <BotFormModal
        mode="create"
        onClose={() => setCreateOpen(false)}
        onSaved={(bot) => {
          setCreateOpen(false);
          router.push(`/bots/${bot.id}/manage`);
        }}
        open={createOpen}
      />
    </div>
  );
}

export default function BotsPage() {
  return <ProtectedRoute>{(user) => <BotsLanding user={user} />}</ProtectedRoute>;
}
