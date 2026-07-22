"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AppNav } from "@/components/AppNav";
import { ChatWorkspace } from "@/components/ChatWorkspace";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { api, ApiError } from "@/lib/api";
import type { BotDetail, SessionUser } from "@/lib/types";

function BotChat({ user, botId }: { user: SessionUser; botId: string }) {
  const [bot, setBot] = useState<BotDetail | null>(null);
  const [error, setError] = useState("");
  const newChatRef = useRef<(() => void) | null>(null);
  const isAdmin = user.role === "ADMIN";
  const canChat = bot?.is_active === true;

  useEffect(() => {
    async function load() {
      try {
        setBot(await api.bot(botId));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Unable to load this bot.");
      }
    }
    void load();
  }, [botId]);

  return (
    <div className="app-shell flex h-screen flex-col">
      <AppNav user={user} />
      <main className="mx-auto flex min-h-0 w-full max-w-7xl flex-1 flex-col gap-4 px-4 py-4 lg:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <Link
              className="text-xs font-semibold text-[var(--primary)] underline-offset-2 hover:underline"
              href="/bots"
            >
              ← All bots
            </Link>
            <h1 className="page-title mt-2 text-2xl">
              {bot?.name ?? "Loading bot..."}
            </h1>
            {bot?.description ? (
              <p className="mt-1 text-sm text-slate-500">{bot.description}</p>
            ) : null}
          </div>
          <button
            className="btn btn-primary"
            disabled={!canChat}
            onClick={() => newChatRef.current?.()}
            type="button"
          >
            New chat
          </button>
        </div>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            {error}
          </div>
        ) : null}

        {canChat ? (
          <ChatWorkspace
            botId={botId}
            heading={`Chat with ${bot.name}`}
            newChatRef={newChatRef}
            subheading="Answers stream live and cite the source file and page from this bot's documents."
          />
        ) : !error && bot ? (
          <div className="panel grid flex-1 place-items-center px-6 py-12 text-center">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-slate-900">
                This bot is inactive.
              </h2>
              {isAdmin ? (
                <Link className="btn btn-secondary mt-5" href={`/bots/${bot.id}/manage`}>
                  Manage bot
                </Link>
              ) : null}
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}

export default function BotChatPage() {
  const params = useParams<{ botId: string }>();
  const botId = params?.botId;
  return (
    <ProtectedRoute>
      {(user) =>
        botId ? (
          <BotChat botId={botId} user={user} />
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
