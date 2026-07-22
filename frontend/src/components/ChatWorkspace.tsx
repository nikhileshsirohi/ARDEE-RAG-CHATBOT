"use client";

import { FormEvent, MutableRefObject, useCallback, useEffect, useRef, useState } from "react";
import { CitationList } from "@/components/CitationList";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { MarkdownContent } from "@/components/MarkdownContent";
import { api, ApiError, askStream } from "@/lib/api";
import type { ChatMessage, ChatSession, Citation } from "@/lib/types";

/** Retrieval is fixed at 3 chunks — no user-facing selector. */
const DEFAULT_TOP_K = 3;

type UiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
  meta?: {
    total_tokens: number;
    latency_ms: number;
    semantic_cache_hit: boolean;
  };
};

function formatDate(value: string | null) {
  if (!value) {
    return "No messages yet";
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function fromHistory(messages: ChatMessage[]): UiMessage[] {
  // The API serializes roles in upper case (USER/ASSISTANT/SYSTEM); normalize
  // to the lower-case union the UI renders and drop system turns.
  return messages
    .map((message) => ({ message, role: String(message.role).toLowerCase() }))
    .filter(({ role }) => role === "user" || role === "assistant")
    .map(({ message, role }) => ({
      id: message.id,
      role: role as "user" | "assistant",
      content: message.content,
      citations: message.source_citations,
    }));
}

export function ChatWorkspace({
  heading,
  subheading,
  botId,
  onActivity,
  newChatRef,
}: {
  heading: string;
  subheading: string;
  botId?: string;
  onActivity?: () => void;
  newChatRef?: MutableRefObject<(() => void) | null>;
}) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [pendingDelete, setPendingDelete] = useState<ChatSession | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const activeSessionIdRef = useRef<string | null>(null);
  activeSessionIdRef.current = activeSessionId;

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const node = scrollRef.current;
      if (node) {
        node.scrollTop = node.scrollHeight;
      }
    });
  }, []);

  const loadSessions = useCallback(async () => {
    const rows = await api.sessions(botId);
    setSessions(rows);
    return rows;
  }, [botId]);

  const loadSession = useCallback(async (sessionId: string) => {
    setError("");
    const detail = await api.session(sessionId);
    setActiveSessionId(sessionId);
    setMessages(fromHistory(detail.messages));
  }, []);

  useEffect(() => {
    async function boot() {
      try {
        const rows = await loadSessions();
        if (rows[0]) {
          await loadSession(rows[0].id);
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Unable to load sessions.");
      } finally {
        setLoading(false);
      }
    }
    void boot();
  }, [loadSessions, loadSession]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const newChat = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setError("");
  }, []);

  useEffect(() => {
    if (!newChatRef) {
      return;
    }
    newChatRef.current = newChat;
    return () => {
      newChatRef.current = null;
    };
  }, [newChat, newChatRef]);

  async function submitQuestion(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || asking) {
      return;
    }
    setQuestion("");
    setError("");
    setAsking(true);

    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", content: trimmed },
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);

    try {
      await askStream(
        {
          question: trimmed,
          bot_id: botId,
          session_id: activeSessionIdRef.current,
          top_k: DEFAULT_TOP_K,
        },
        {
          onEvent: (streamEvent) => {
            if (streamEvent.type === "meta") {
              setActiveSessionId(streamEvent.session_id);
            } else if (streamEvent.type === "token") {
              setMessages((current) =>
                current.map((message) =>
                  message.id === assistantId
                    ? { ...message, content: message.content + streamEvent.text }
                    : message,
                ),
              );
              scrollToBottom();
            } else if (streamEvent.type === "done") {
              setMessages((current) =>
                current.map((message) =>
                  message.id === assistantId
                    ? {
                        ...message,
                        content: streamEvent.answer,
                        streaming: false,
                        citations: streamEvent.source_citations,
                        meta: {
                          total_tokens: streamEvent.total_tokens,
                          latency_ms: streamEvent.latency_ms,
                          semantic_cache_hit: streamEvent.semantic_cache_hit,
                        },
                      }
                    : message,
                ),
              );
            } else if (streamEvent.type === "error") {
              throw new Error(streamEvent.message);
            }
          },
        },
      );
      await loadSessions();
      onActivity?.();
    } catch (err) {
      const messageText = err instanceof Error ? err.message : "Unable to ask the chatbot.";
      setError(messageText);
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId && message.streaming
            ? { ...message, streaming: false, content: message.content || "(no response)" }
            : message,
        ),
      );
    } finally {
      setAsking(false);
    }
  }

  function startRename(session: ChatSession) {
    setRenamingId(session.id);
    setRenameValue(session.title);
  }

  async function saveRename(sessionId: string) {
    const title = renameValue.trim();
    if (!title) {
      return;
    }
    try {
      await api.renameSession(sessionId, title);
      setRenamingId(null);
      await loadSessions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Rename failed.");
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) {
      return;
    }
    setDeleteBusy(true);
    try {
      await api.deleteSession(pendingDelete.id);
      if (activeSessionIdRef.current === pendingDelete.id) {
        newChat();
      }
      setPendingDelete(null);
      await loadSessions();
      onActivity?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed.");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[300px_1fr]">
      <aside className="panel flex min-h-0 flex-col p-3">
        <div className="mb-3 px-1">
          <h2 className="text-base font-semibold tracking-tight text-slate-950">Sessions</h2>
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {loading ? <div className="px-1 text-sm text-slate-500">Loading sessions...</div> : null}
          {!loading && sessions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--line-strong)] bg-white/40 p-4 text-sm text-slate-500">
              Ask a question to create your first chat session.
            </div>
          ) : null}
          {sessions.map((session) => {
            const active = session.id === activeSessionId;
            if (renamingId === session.id) {
              return (
                <div
                  className="rounded-lg border border-[var(--primary)] bg-white p-2 shadow-sm"
                  key={session.id}
                >
                  <input
                    autoFocus
                    className="input"
                    onChange={(event) => setRenameValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        void saveRename(session.id);
                      }
                      if (event.key === "Escape") {
                        setRenamingId(null);
                      }
                    }}
                    value={renameValue}
                  />
                  <div className="mt-2 flex gap-2">
                    <button
                      className="btn btn-primary flex-1"
                      onClick={() => void saveRename(session.id)}
                      type="button"
                    >
                      Save
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={() => setRenamingId(null)}
                      type="button"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              );
            }
            return (
              <div
                className={`session-item group ${active ? "session-item-active" : ""}`}
                key={session.id}
              >
                <button
                  className="block w-full px-3 py-2.5 text-left"
                  onClick={() => void loadSession(session.id)}
                  type="button"
                >
                  <div className="truncate text-sm font-semibold text-slate-900">{session.title}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium text-slate-500">
                    <span className="truncate">{formatDate(session.last_message_at)}</span>
                    <span className="text-slate-300" aria-hidden>
                      ·
                    </span>
                    <span className="tabular-nums text-slate-600">
                      {new Intl.NumberFormat().format(session.total_tokens ?? 0)} tokens
                    </span>
                  </div>
                </button>
                <div className="flex gap-1 border-t border-[var(--line)] px-2 py-1">
                  <button
                    className="rounded px-2 py-1 text-xs font-semibold text-slate-500 hover:bg-white/80 hover:text-slate-800"
                    onClick={() => startRename(session)}
                    type="button"
                  >
                    Rename
                  </button>
                  <button
                    className="rounded px-2 py-1 text-xs font-semibold text-[var(--danger)] hover:bg-red-50"
                    onClick={() => setPendingDelete(session)}
                    type="button"
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </aside>

      <section className="panel flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-[var(--line)] px-4 py-3.5">
          <h1 className="text-lg font-semibold tracking-tight text-slate-950">{heading}</h1>
          <p className="mt-0.5 text-sm text-slate-500">{subheading}</p>
        </div>

        <div
          className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-[var(--surface-subtle)]/80 p-4"
          ref={scrollRef}
        >
          {messages.length === 0 && !loading ? (
            <div className="grid h-full min-h-72 place-items-center text-center">
              <div className="animate-rise">
                <h2 className="page-title text-2xl">Ask your documents</h2>
                <p className="page-lede mx-auto">
                  Answers stream live and are grounded in the uploaded PDFs, with citations to the
                  exact file and page. Retrieval uses the top 3 chunks.
                </p>
              </div>
            </div>
          ) : null}
          {messages.map((message) => (
            <div
              className={message.role === "user" ? "chat-bubble-user" : "chat-bubble-assistant"}
              key={message.id}
            >
              <div className="mb-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.08em] text-slate-500">
                {message.role === "user" ? "You" : "Assistant"}
              </div>
              {message.role === "assistant" ? (
                <MarkdownContent content={message.content} streaming={message.streaming} />
              ) : (
                <div className="whitespace-pre-wrap text-sm leading-6 text-slate-800">
                  {message.content}
                </div>
              )}
              {message.meta ? (
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <span className="badge">
                    Cache {message.meta.semantic_cache_hit ? "hit" : "miss"}
                  </span>
                  <span className="badge">
                    {new Intl.NumberFormat().format(message.meta.total_tokens)} tokens
                  </span>
                  <span className="badge">{message.meta.latency_ms} ms</span>
                </div>
              ) : null}
              {message.role === "assistant" && !message.streaming ? (
                <CitationList citations={message.citations} />
              ) : null}
            </div>
          ))}
        </div>

        <form className="border-t border-[var(--line)] bg-white/80 p-3 backdrop-blur-sm" onSubmit={submitQuestion}>
          {error ? (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
              {error}
            </div>
          ) : null}
          <div className="flex flex-col gap-3 sm:flex-row">
            <textarea
              className="input min-h-20 flex-1 resize-y"
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submitQuestion(event);
                }
              }}
              placeholder="Ask a question about your uploaded PDFs..."
              value={question}
            />
            <button className="btn btn-primary sm:w-32" disabled={asking} type="submit">
              {asking ? "Streaming..." : "Ask"}
            </button>
          </div>
        </form>
      </section>

      <ConfirmDialog
        busy={deleteBusy}
        confirmLabel="Delete session"
        message={
          <>
            Delete <span className="font-black text-slate-800">{pendingDelete?.title}</span> and all
            of its messages? This cannot be undone.
          </>
        }
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void confirmDelete()}
        open={pendingDelete !== null}
        title="Delete chat session"
        tone="danger"
      />
    </div>
  );
}
