"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { api, ApiError } from "@/lib/api";
import type { RagDocument } from "@/lib/types";

function statusClass(status: string) {
  const normalized = status.toUpperCase();
  if (normalized === "READY") {
    return "status-pill status-ready";
  }
  if (normalized === "FAILED") {
    return "status-pill status-failed";
  }
  if (normalized === "PROCESSING" || normalized === "PENDING") {
    return "status-pill status-pending";
  }
  return "status-pill";
}

function formatStatus(status: string) {
  const normalized = status.toLowerCase();
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

function titleFromFile(file: File) {
  const name = file.name.trim();
  return name.replace(/\.pdf$/i, "") || name;
}

function PdfGlyph() {
  return (
    <svg
      aria-hidden
      className="h-5 w-5 shrink-0 text-[var(--danger)]"
      fill="none"
      viewBox="0 0 24 24"
    >
      <path
        d="M7 3.75h6.5L19 9.25V20.25a.75.75 0 0 1-.75.75H7.75A.75.75 0 0 1 7 20.25V3.75Z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path d="M13.5 3.75V9.25H19" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M9 13.5h6M9 16.5h4"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function DocumentsPanel({
  botId,
  onActivity,
}: {
  botId: string;
  onActivity?: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pendingDelete, setPendingDelete] = useState<RagDocument | null>(null);

  const load = useCallback(async () => {
    const rows = await api.botDocuments(botId);
    setDocuments(rows);
  }, [botId]);

  useEffect(() => {
    async function boot() {
      try {
        await load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Unable to load documents.");
      } finally {
        setLoading(false);
      }
    }
    void boot();
  }, [load]);

  async function uploadFiles(files: FileList | File[]) {
    const pdfs = Array.from(files).filter((file) => file.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length === 0) {
      setError("Choose one or more PDF files.");
      return;
    }

    setBusy(true);
    setError("");
    setNotice("");
    try {
      for (const file of pdfs) {
        await api.uploadBotDocument(botId, { title: titleFromFile(file), file });
      }
      setNotice(
        pdfs.length === 1 ? `Uploaded “${pdfs[0].name}”.` : `Uploaded ${pdfs.length} PDFs.`,
      );
      await load();
      onActivity?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
      await load();
    } finally {
      setBusy(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.deleteDocument(pendingDelete.id);
      setNotice(`Deleted “${pendingDelete.title}”.`);
      setPendingDelete(null);
      await load();
      onActivity?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-panel p-0">
      <div className="admin-section-head">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-slate-950">Knowledge</h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            PDFs this bot can search and cite in answers.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            accept="application/pdf"
            className="sr-only"
            disabled={busy}
            multiple
            onChange={(event) => {
              const files = event.target.files;
              if (files?.length) {
                void uploadFiles(files);
              }
            }}
            ref={fileInputRef}
            type="file"
          />
          <button
            className="btn btn-primary"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
            type="button"
          >
            {busy ? "Uploading..." : "+ Add knowledge"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="mx-4 mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mx-4 mt-4 rounded-lg border border-[var(--primary-soft-border)] bg-[var(--accent-soft)] px-3 py-2 text-sm font-semibold text-[var(--accent)]">
          {notice}
        </div>
      ) : null}

      <div className="table-wrap px-2 pb-2">
        <table>
          <thead>
            <tr>
              <th className="min-w-64">Name</th>
              <th>Last updated</th>
              <th>Status</th>
              <th className="w-14">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.id}>
                <td>
                  <div className="flex items-center gap-3">
                    <PdfGlyph />
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-slate-900">
                        {document.original_filename || document.title}
                      </div>
                      {document.page_count ? (
                        <div className="mt-0.5 text-xs text-slate-500">
                          {document.page_count} {document.page_count === 1 ? "page" : "pages"}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </td>
                <td className="whitespace-nowrap text-sm text-slate-600">
                  {formatDate(document.updated_at)}
                </td>
                <td>
                  <span className={statusClass(document.status)}>
                    {formatStatus(document.status)}
                  </span>
                </td>
                <td>
                  <button
                    aria-label={`Delete ${document.title}`}
                    className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition hover:bg-red-50 hover:text-[var(--danger)]"
                    disabled={busy}
                    onClick={() => setPendingDelete(document)}
                    type="button"
                  >
                    <span aria-hidden className="text-lg leading-none">
                      ×
                    </span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading ? (
          <div className="p-5 text-sm text-slate-500">Loading documents...</div>
        ) : null}
        {!loading && documents.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <p className="text-sm font-semibold text-slate-800">No knowledge sources yet</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">
              Add a PDF to ground this bot’s answers in your documents.
            </p>
            <button
              className="btn btn-primary mt-4"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
              type="button"
            >
              + Add knowledge
            </button>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        busy={busy}
        confirmLabel="Delete"
        message={
          <>
            Delete <span className="font-semibold text-slate-800">{pendingDelete?.title}</span> and
            remove it from search? This cannot be undone.
          </>
        }
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void confirmDelete()}
        open={pendingDelete !== null}
        title="Delete document"
        tone="danger"
      />
    </div>
  );
}
