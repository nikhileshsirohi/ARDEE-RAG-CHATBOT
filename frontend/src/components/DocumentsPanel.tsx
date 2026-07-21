"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { api, ApiError } from "@/lib/api";
import type { RagDocument } from "@/lib/types";

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

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

type RowState = {
  title: string;
  file: File | null;
};

type PendingUpdate = { document: RagDocument; title: string; file: File | null };

export function DocumentsPanel({ onActivity }: { onActivity?: () => void }) {
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [rowState, setRowState] = useState<Record<string, RowState>>({});
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pendingUpdate, setPendingUpdate] = useState<PendingUpdate | null>(null);
  const [pendingDelete, setPendingDelete] = useState<RagDocument | null>(null);

  const load = useCallback(async () => {
    const rows = await api.documents();
    setDocuments(rows);
    setRowState(
      Object.fromEntries(rows.map((doc) => [doc.id, { title: doc.title, file: null }])),
    );
  }, []);

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

  function setRow(id: string, patch: Partial<RowState>) {
    setRowState((current) => ({ ...current, [id]: { ...current[id], ...patch } }));
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    const title = uploadTitle.trim();
    if (!title) {
      setError("A document name is required to upload a PDF.");
      return;
    }
    if (!uploadFile) {
      setError("Choose a PDF file to upload.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.uploadDocument({ title, file: uploadFile });
      setUploadTitle("");
      setUploadFile(null);
      setNotice(`Uploaded “${title}”.`);
      await load();
      onActivity?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  function requestUpdate(document: RagDocument) {
    const state = rowState[document.id];
    const title = state?.title.trim() ?? "";
    const file = state?.file ?? null;
    if (!title) {
      setError("Document name cannot be empty.");
      return;
    }
    if (title === document.title && !file) {
      setError("Change the name or choose a new PDF before updating.");
      return;
    }
    setError("");
    setPendingUpdate({ document, title, file });
  }

  async function confirmUpdate() {
    if (!pendingUpdate) {
      return;
    }
    const { document, title, file } = pendingUpdate;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (title !== document.title) {
        await api.updateDocument(document.id, { title });
      }
      if (file) {
        await api.replaceDocumentFile(document.id, file);
      }
      setPendingUpdate(null);
      setNotice(`Updated “${title}”.`);
      await load();
      onActivity?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Update failed.");
    } finally {
      setBusy(false);
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
          <h2 className="text-lg font-black text-slate-950">RAG documents</h2>
          <p className="text-sm text-slate-500">
            Upload PDFs (name required), replace a file with a new one, rename, or delete. Updates
            and deletes ask for confirmation.
          </p>
        </div>
        <button className="btn btn-secondary" disabled={busy} onClick={() => void load()} type="button">
          Refresh
        </button>
      </div>

      <form className="grid gap-3 border-b border-slate-200 p-4 lg:grid-cols-[1fr_1fr_auto]" onSubmit={upload}>
        <label className="block">
          <span className="mb-1 block text-xs font-black uppercase text-slate-500">
            Document name<span className="text-[#bb3e3e]"> *</span>
          </span>
          <input
            className="input"
            onChange={(event) => setUploadTitle(event.target.value)}
            placeholder="e.g. Employee Handbook 2026"
            required
            value={uploadTitle}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-black uppercase text-slate-500">PDF file *</span>
          <input
            accept="application/pdf"
            className="input"
            onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>
        <div className="flex items-end">
          <button className="btn btn-primary w-full" disabled={busy} type="submit">
            Upload PDF
          </button>
        </div>
      </form>

      {error ? (
        <div className="mx-4 mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mx-4 mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700">
          {notice}
        </div>
      ) : null}

      <div className="table-wrap p-2">
        <table>
          <thead>
            <tr>
              <th className="min-w-64">Name &amp; file</th>
              <th>Status</th>
              <th>Pages</th>
              <th>Chunks</th>
              <th>Replacement PDF</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => {
              const state = rowState[document.id] ?? { title: document.title, file: null };
              return (
                <tr key={document.id}>
                  <td>
                    <input
                      className="input min-w-56"
                      onChange={(event) => setRow(document.id, { title: event.target.value })}
                      value={state.title}
                    />
                    <div className="mt-1 text-xs font-semibold text-slate-500">
                      {document.original_filename} · v{document.version}
                    </div>
                  </td>
                  <td>
                    <span className={statusClass(document.status)}>{document.status}</span>
                  </td>
                  <td>{document.page_count ?? "n/a"}</td>
                  <td>{formatNumber(document.chunk_count)}</td>
                  <td>
                    <input
                      accept="application/pdf"
                      className="input min-w-52"
                      key={`${document.id}-${document.version}`}
                      onChange={(event) =>
                        setRow(document.id, { file: event.target.files?.[0] ?? null })
                      }
                      type="file"
                    />
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-2">
                      <button
                        className="btn btn-primary"
                        disabled={busy}
                        onClick={() => requestUpdate(document)}
                        type="button"
                      >
                        Update
                      </button>
                      <button
                        className="btn btn-danger"
                        disabled={busy}
                        onClick={() => setPendingDelete(document)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!loading && documents.length === 0 ? (
          <div className="p-5 text-sm text-slate-500">No RAG files uploaded yet.</div>
        ) : null}
      </div>

      <ConfirmDialog
        busy={busy}
        confirmLabel="Apply update"
        message={
          <>
            Update <span className="font-black text-slate-800">{pendingUpdate?.document.title}</span>?
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {pendingUpdate && pendingUpdate.title !== pendingUpdate.document.title ? (
                <li>
                  Rename to <span className="font-bold">“{pendingUpdate.title}”</span>
                </li>
              ) : null}
              {pendingUpdate?.file ? (
                <li>
                  Replace the PDF with{" "}
                  <span className="font-bold">{pendingUpdate.file.name}</span> and re-index it
                </li>
              ) : null}
            </ul>
          </>
        }
        onCancel={() => setPendingUpdate(null)}
        onConfirm={() => void confirmUpdate()}
        open={pendingUpdate !== null}
        title="Confirm document update"
        tone="primary"
      />

      <ConfirmDialog
        busy={busy}
        confirmLabel="Delete document"
        message={
          <>
            Delete <span className="font-black text-slate-800">{pendingDelete?.title}</span> and
            remove it from search? This cannot be undone.
          </>
        }
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void confirmDelete()}
        open={pendingDelete !== null}
        title="Confirm document delete"
        tone="danger"
      />
    </div>
  );
}
