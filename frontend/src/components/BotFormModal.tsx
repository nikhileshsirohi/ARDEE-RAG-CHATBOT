"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Bot } from "@/lib/types";

const PROMPT_PLACEHOLDER =
  "e.g. You are the ACME HR assistant. Answer employee questions about company " +
  "policies using only the attached handbook. Be friendly and concise.";

export function BotFormModal({
  mode,
  bot,
  open,
  onClose,
  onSaved,
}: {
  mode: "create" | "edit";
  bot?: Bot | null;
  open: boolean;
  onClose: () => void;
  onSaved: (bot: Bot) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) {
      return;
    }
    setName(bot?.name ?? "");
    setDescription(bot?.description ?? "");
    setSystemPrompt(bot?.system_prompt ?? "");
    setError("");
  }, [open, bot]);

  if (!open) {
    return null;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
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
    setBusy(true);
    setError("");
    try {
      const payload = {
        name: trimmedName,
        description: description.trim() || undefined,
        system_prompt: trimmedPrompt,
      };
      const saved =
        mode === "create"
          ? await api.createBot(payload)
          : await api.updateBot(bot!.id, payload);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to save the bot.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Bot form">
      <div className="modal-card" style={{ maxWidth: "34rem" }}>
        <h3 className="text-lg font-black text-slate-950">
          {mode === "create" ? "Create a bot" : "Edit bot"}
        </h3>
        <p className="mt-1 text-sm text-slate-500">
          {mode === "create"
            ? "Give your bot a name and a prompt. You can attach PDF documents next."
            : "Update the bot name, description, and prompt."}
        </p>
        <form className="mt-4 space-y-4" onSubmit={onSubmit}>
          <label className="block text-sm font-bold text-slate-700">
            Title
            <input
              autoFocus
              className="input mt-1"
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. HR Policy Assistant"
              value={name}
            />
          </label>
          <label className="block text-sm font-bold text-slate-700">
            Description <span className="font-semibold text-slate-400">(optional)</span>
            <input
              className="input mt-1"
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Short summary shown on the bot card"
              value={description}
            />
          </label>
          <label className="block text-sm font-bold text-slate-700">
            Prompt
            <textarea
              className="input mt-1 min-h-32 resize-y"
              onChange={(event) => setSystemPrompt(event.target.value)}
              placeholder={PROMPT_PLACEHOLDER}
              value={systemPrompt}
            />
          </label>
          {error ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
              {error}
            </div>
          ) : null}
          <div className="flex justify-end gap-2">
            <button
              className="btn btn-secondary"
              disabled={busy}
              onClick={onClose}
              type="button"
            >
              Cancel
            </button>
            <button className="btn btn-primary" disabled={busy} type="submit">
              {busy ? "Saving..." : mode === "create" ? "Create bot" : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
