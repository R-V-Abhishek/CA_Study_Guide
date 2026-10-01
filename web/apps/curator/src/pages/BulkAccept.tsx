import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Check, FolderOpen } from "lucide-react";
import { curatorClient, requiredData } from "../lib/client";
import { RequestError } from "../components/RequestError";

export function BulkAccept() {
  const queryClient = useQueryClient();
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Fetch confirmed documents
  const { data: documents = [], isLoading, error, refetch } = useQuery({
    queryKey: ["curate-docs-bulk"],
    queryFn: async () => {
      return requiredData(await curatorClient.GET("/api/v1/curate/documents", { params: { query: { status: "confirmed" } } }));
    },
  });

  // Bulk accept mutation
  const bulkAcceptMutation = useMutation({
    mutationFn: async (docId: number) => {
      const res = await curatorClient.POST(
        "/api/v1/curate/documents/{doc_id}/bulk_accept_bucket_a",
        {
          params: { path: { doc_id: docId } },
        }
      );
      return requiredData(res);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["curator-queue"] });
      queryClient.invalidateQueries({ queryKey: ["curate-docs-bulk"] });
      setSuccessMsg(
        `Successfully published ${data.accepted_count} Bucket A units to core.appearance!`
      );
      setTimeout(() => setSuccessMsg(null), 5000);
    },
  });

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in duration-150">
      <div>
        <h1 className="text-xl font-bold text-white">Bulk Accept — Bucket A Consensus</h1>
        <p className="text-xs text-slate-400 mt-1">
          Approve the Bucket A recommendations in a confirmed document.
        </p>
      </div>

      <RequestError error={error} retry={() => void refetch()} />
      <RequestError error={bulkAcceptMutation.error} />
      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-950/60 border border-emerald-700/80 text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in duration-200">
          <Check className="w-4 h-4 text-emerald-400" />
          <span>{successMsg}</span>
        </div>
      )}

      {isLoading ? (
        <div className="p-12 text-center text-slate-400 space-y-3">
          <div className="h-6 w-48 bg-slate-800 rounded animate-pulse mx-auto" />
          <div className="h-32 w-full bg-slate-800 rounded-2xl animate-pulse" />
        </div>
      ) : error ? null : documents.length === 0 ? (
        <div className="p-12 text-center bg-[#1E293B] rounded-2xl border border-[#334155] space-y-3">
          <CheckCheck className="w-10 h-10 text-emerald-400 mx-auto" />
          <h2 className="font-bold text-white text-base">No Confirmed Documents Pending</h2>
          <p className="text-xs text-slate-400">
            Confirm catalogue metadata first in the Document Catalogue to unlock bulk approval.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="p-6 rounded-2xl bg-[#1E293B] border border-[#334155] flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-700">
                    {doc.paper_id ?? "Paper unavailable"}
                  </span>
                  <span className="text-xs font-semibold text-white">
                    {doc.attempt_id ?? "Attempt unavailable"} · {doc.doc_type_id ?? "Document type unavailable"}
                  </span>
                </div>
                <h3 className="font-semibold text-sm text-slate-200">{doc.title ?? "Title unavailable"}</h3>
                <div className="text-[11px] text-slate-400 flex items-center gap-2">
                  <FolderOpen className="w-3.5 h-3.5 text-slate-500" />
                  <span>Document ID #{doc.id}</span>
                </div>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <button
                  type="button"
                  onClick={() => { if (!bulkAcceptMutation.isPending) { setSuccessMsg(null); bulkAcceptMutation.mutate(doc.id); } }}
                  disabled={bulkAcceptMutation.isPending}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition-colors shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  <CheckCheck className="w-4 h-4" />
                  <span>Accept All Bucket A Units</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
