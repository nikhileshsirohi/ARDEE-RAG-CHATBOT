import type { Citation } from "@/lib/types";

/**
 * Renders the source citations attached to an assistant answer:
 * which file, which page, and the retrieval scores.
 */
export function CitationList({ citations }: { citations?: Citation[] }) {
  if (!citations?.length) {
    return null;
  }
  return (
    <div className="mt-3">
      <div className="mb-2 text-xs font-black uppercase tracking-wide text-slate-500">
        Citations ({citations.length})
      </div>
      <div className="space-y-2">
        {citations.map((citation, index) => (
          <div
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600"
            key={`${citation.chunk_id ?? index}`}
          >
            <div className="font-black text-slate-800">
              [{citation.source_number ?? index + 1}] {citation.document_title ?? "Document"}
            </div>
            <div className="mt-0.5">
              <span className="font-semibold text-slate-700">
                {citation.original_filename ?? "PDF"}
              </span>
              {citation.page_number ? ` · page ${citation.page_number}` : " · page n/a"}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
              {typeof citation.hybrid_score === "number" ? (
                <span>Hybrid {citation.hybrid_score.toFixed(3)}</span>
              ) : null}
              {typeof citation.vector_score === "number" ? (
                <span>Vector {citation.vector_score.toFixed(3)}</span>
              ) : null}
              {typeof citation.keyword_score === "number" ? (
                <span>Keyword {citation.keyword_score.toFixed(3)}</span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
