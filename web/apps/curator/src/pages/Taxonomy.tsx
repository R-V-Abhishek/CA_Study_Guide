import { accountKey } from "@caf/api-client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Network, ChevronDown, ChevronRight, Hash } from "lucide-react";
import { curatorClient, requiredData } from "../lib/client";
import { RequestError } from "../components/RequestError";

export function Taxonomy() {
  const [selectedPaper, setSelectedPaper] = useState("");
  const [expandedChapters, setExpandedChapters] = useState<Record<string, boolean>>({});

  const papers = useQuery({ queryKey: ["curator-papers", accountKey()], queryFn: async () => requiredData(await curatorClient.GET("/api/v1/papers")) });
  const paperId = selectedPaper || papers.data?.[0]?.id;
  const { data: treeData, isLoading, error, refetch } = useQuery({
    queryKey: ["curator-taxonomy-tree", accountKey(), paperId],
    enabled: Boolean(paperId),
    queryFn: async () => {
      return requiredData(await curatorClient.GET("/api/v1/tree", { params: { query: { paper: paperId! } } }));
    },
  });

  const toggleChapter = (chId: string) => {
    setExpandedChapters((prev) => ({
      ...prev,
      [chId]: !prev[chId],
    }));
  };

  const chapters = treeData?.chapters || [];

  return (
    <div className="space-y-5 animate-in fade-in duration-150">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-[#334155]">
        <div>
          <div className="flex items-center gap-2">
            <Network className="w-5 h-5 text-indigo-400" />
            <h1 className="text-lg font-bold text-white">Taxonomy Explorer</h1>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Current syllabus hierarchy from the backend.
          </p>
        </div>

        {/* Paper selector tabs */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-900 border border-slate-700">
          {papers.data?.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setSelectedPaper(p.id)}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-bold transition-colors ${
                paperId === p.id
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {p.code}
            </button>
          ))}
        </div>
      </div>

      <RequestError error={papers.error} retry={() => void papers.refetch()} />
      <RequestError error={error} retry={() => void refetch()} />
      {/* Chapters & Topics List */}
      <div className="rounded-2xl border border-[#334155] bg-[#1E293B] overflow-hidden shadow-sm">
        {isLoading || papers.isPending ? (
          <div className="p-12 text-center text-slate-400 space-y-3">
            <div className="h-6 w-48 bg-slate-800 rounded animate-pulse mx-auto" />
            <div className="h-48 w-full bg-slate-800 rounded animate-pulse" />
          </div>
        ) : error || papers.error ? null : chapters.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-500">
            No taxonomy chapters loaded for this paper.
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {chapters.map((chapter) => {
              const isExpanded = expandedChapters[chapter.id] ?? false;

              return (
                <div key={chapter.id} className="text-xs">
                  {/* Chapter header */}
                  <button
                    type="button"
                    onClick={() => toggleChapter(chapter.id)}
                    className="w-full p-4 flex items-center justify-between text-left hover:bg-slate-800/40 transition-colors"
                  >
                    <div className="flex items-center gap-2.5 truncate pr-3">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                      )}
                      <span className="font-mono text-xs font-bold text-indigo-400">
                        {chapter.id}
                      </span>
                      <span className="font-bold text-white truncate">
                        {chapter.name}
                      </span>
                    </div>

                    <div className="flex items-center gap-4 shrink-0 font-mono text-[11px] text-slate-400">
                      {chapter.weightage_min_pct != null && (
                        <span>
                          {chapter.weightage_min_pct}–{chapter.weightage_max_pct}% weightage
                        </span>
                      )}
                      <span className="font-semibold text-slate-300">
                        {chapter.total_subtopics} subtopics
                      </span>
                    </div>
                  </button>

                  {/* Topics and Subtopics */}
                  {isExpanded && (
                    <div className="px-8 pb-3 space-y-3 bg-slate-900/40 border-t border-slate-800/60 pt-3">
                      {(chapter.topics || []).map((topic) => (
                        <div key={topic.id} className="space-y-1.5">
                          <div className="flex items-center gap-2 text-slate-300 font-semibold text-xs">
                            <span className="font-mono text-indigo-300 text-[11px]">
                              {topic.id}
                            </span>
                            <span>{topic.name}</span>
                          </div>

                          <div className="space-y-1 pl-4 border-l border-slate-800">
                            {(topic.subtopics || []).map((sub) => (
                              <div
                                key={sub.id}
                                className="flex items-center justify-between py-1 px-2.5 rounded hover:bg-slate-800/40 transition-colors text-[11px] text-slate-400 font-mono"
                              >
                                <div className="flex items-center gap-2 truncate pr-2">
                                  <Hash className="w-3 h-3 text-slate-500 shrink-0" />
                                  <span className="text-indigo-400 shrink-0 font-bold">
                                    {sub.id}
                                  </span>
                                  <span className="text-slate-200 font-sans truncate">
                                    {sub.name}
                                  </span>
                                </div>
                                <span className="shrink-0 text-slate-500">
                                  seq #{sub.seq}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
