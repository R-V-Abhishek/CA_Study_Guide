import { accountKey } from "@caf/api-client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FolderOpen,
  CheckCircle2,
  XCircle,
  Clock,
  Filter,
} from "lucide-react";
import { curatorClient, requiredData } from "../lib/client";
import { RequestError } from "../components/RequestError";

export function Catalogue() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [paperFilter, setPaperFilter] = useState<string>("all");

  const { data: documents = [], isLoading, error, refetch } = useQuery({
    queryKey: ["curate-catalogue", accountKey(), statusFilter, paperFilter],
    queryFn: async () => {
      return requiredData(await curatorClient.GET("/api/v1/curate/documents", { params: { query: { ...(statusFilter !== "all" ? { status: statusFilter } : {}), ...(paperFilter !== "all" ? { paper_id: paperFilter } : {}) } } }));
    },
  });

  const papers = useQuery({ queryKey: ["curator-papers", accountKey()], queryFn: async () => requiredData(await curatorClient.GET("/api/v1/papers")) });

  // Confirm document mutation
  const confirmMutation = useMutation({
    mutationFn: async (docId: number) => {
      const res = await curatorClient.POST(
        "/api/v1/curate/documents/{doc_id}/confirm",
        {
          params: { path: { doc_id: docId } },
        }
      );
      return requiredData(res);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["curate-catalogue", accountKey()] });
      queryClient.invalidateQueries({ queryKey: ["curate-docs-bulk", accountKey()] });
    },
  });

  // Reject document mutation
  const rejectMutation = useMutation({
    mutationFn: async (docId: number) => {
      const res = await curatorClient.POST(
        "/api/v1/curate/documents/{doc_id}/reject",
        {
          params: { path: { doc_id: docId } },
        }
      );
      return requiredData(res);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["curate-catalogue", accountKey()] });
    },
  });

  return (
    <div className="space-y-5 animate-in fade-in duration-150">
      {/* Header and Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-[#334155]">
        <div>
          <div className="flex items-center gap-2">
            <FolderOpen className="w-5 h-5 text-indigo-400" />
            <h1 className="text-lg font-bold text-white">Document Catalogue</h1>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Verified PDF documents, hash deduplication, and extraction tracking.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
            <Filter className="w-3.5 h-3.5" />
            <span>Filter:</span>
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-2.5 py-1 rounded-lg text-xs bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none"
          >
            <option value="all">All Catalog Statuses</option>
            <option value="confirmed">Confirmed Only</option>
            <option value="inferred">Inferred (Pending Review)</option>
            <option value="rejected">Rejected</option>
          </select>

          <select
            value={paperFilter}
            onChange={(e) => setPaperFilter(e.target.value)}
            className="px-2.5 py-1 rounded-lg text-xs bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none"
          >
            <option value="all">All Papers</option>
            {papers.data?.map(paper => <option key={paper.id} value={paper.id}>{paper.code} — {paper.name}</option>)}
          </select>
        </div>
      </div>

      <RequestError error={error} retry={() => void refetch()} />
      <RequestError error={papers.error} retry={() => void papers.refetch()} />
      <RequestError error={confirmMutation.error ?? rejectMutation.error} />
      {/* Documents Table */}
      <div className="rounded-2xl border border-[#334155] bg-[#1E293B] overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-12 text-center text-slate-400 space-y-3">
            <div className="h-6 w-48 bg-slate-800 rounded animate-pulse mx-auto" />
            <div className="h-32 w-full bg-slate-800 rounded animate-pulse" />
          </div>
        ) : error ? null : documents.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-400">
            No documents found matching current filter criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-900/60 border-b border-[#334155] text-slate-400 uppercase font-mono text-[10px]">
                <tr>
                  <th className="p-3.5 pl-5">Doc ID</th>
                  <th className="p-3.5">Title</th>
                  <th className="p-3.5">Paper</th>
                  <th className="p-3.5">Attempt</th>
                  <th className="p-3.5">Type</th>
                  <th className="p-3.5">Pages</th>
                  <th className="p-3.5">Status</th>
                  <th className="p-3.5 pr-5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80 font-mono">
                {documents.map((doc) => {
                  const isConfirmed = doc.catalog_status === "confirmed";
                  const isRejected = doc.catalog_status === "rejected";

                  return (
                    <tr
                      key={doc.id}
                      className="hover:bg-slate-800/40 transition-colors"
                    >
                      <td className="p-3.5 pl-5 font-bold text-slate-200">
                        #{doc.id}
                      </td>
                      <td className="p-3.5 font-sans font-medium text-white max-w-xs truncate">
                        {doc.title ?? "Title unavailable"}
                      </td>
                      <td className="p-3.5 font-bold text-indigo-400">
                        {doc.paper_id ?? "Unavailable"}
                      </td>
                      <td className="p-3.5 text-slate-200">
                        {doc.attempt_id ?? "Unavailable"}
                      </td>
                      <td className="p-3.5 text-slate-400 uppercase">
                        {doc.doc_type_id ?? "Unavailable"}
                      </td>
                      <td className="p-3.5 text-slate-400">
                        {doc.page_count === null ? "Unavailable" : `${doc.page_count} pp`}
                      </td>
                      <td className="p-3.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                            isConfirmed
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                              : isRejected
                              ? "bg-rose-950 text-rose-300 border border-rose-800"
                              : "bg-amber-950 text-amber-300 border border-amber-800"
                          }`}
                        >
                          {isConfirmed ? (
                            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          ) : isRejected ? (
                            <XCircle className="w-3 h-3 text-rose-400" />
                          ) : (
                            <Clock className="w-3 h-3 text-amber-400" />
                          )}
                          <span>{doc.catalog_status}</span>
                        </span>
                      </td>
                      <td className="p-3.5 pr-5 text-right font-sans">
                        {!isConfirmed && (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => confirmMutation.mutate(doc.id)}
                              disabled={confirmMutation.isPending || rejectMutation.isPending}
                              className="px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 font-semibold text-white text-[11px] transition-colors"
                            >
                              Confirm
                            </button>
                            <button
                              type="button"
                              onClick={() => rejectMutation.mutate(doc.id)}
                              disabled={confirmMutation.isPending || rejectMutation.isPending}
                              className="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] transition-colors"
                            >
                              Reject
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
