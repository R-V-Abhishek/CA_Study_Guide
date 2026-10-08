import { accountKey, apiRequest, type components } from "@caf/api-client";
import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, X, Check } from "lucide-react";
import { curatorClient, requiredData } from "../lib/client";
import { RequestError } from "./RequestError";

interface SubtopicOption {
  id: string;
  name: string;
  paperCode: string;
  chapterName: string;
  topicName: string;
}

interface NodePickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (nodeId: string) => void;
  currentSelectedId?: string | null;
  taxonomyVersionId?: number;
  paperId?: string;
  candidates?: SubtopicOption[];
}

export function NodePickerModal({
  isOpen,
  onClose,
  onSelect,
  currentSelectedId,
  taxonomyVersionId,
  paperId,
  candidates,
}: NodePickerModalProps) {
  const [search, setSearch] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Auto-focus input when opened
  useEffect(() => {
    if (isOpen) {
      dialogRef.current?.showModal();
      inputRef.current?.focus();
    } else {
      setSearch("");
    }
  }, [isOpen]);

  // Query all subtopics across papers
  const { data: allSubtopics = [], isPending, error, refetch } = useQuery({
    queryKey: ["curator-all-nodes", accountKey(), taxonomyVersionId, paperId],
    queryFn: async () => {
      if (taxonomyVersionId) {
        const releases = await apiRequest<components["schemas"]["ReleaseSummary"][]>("/api/v1/taxonomy/versions");
        const release = releases.find(value => value.taxonomy_version_id === taxonomyVersionId);
        if (!release) throw new Error("Pinned taxonomy revision unavailable");
        const trees = await apiRequest<components["schemas"]["TaxonomyTreeNode"][]>(`/api/v1/taxonomy/versions/${encodeURIComponent(release.version_id)}/tree${paperId ? `?paper_id=${encodeURIComponent(paperId)}` : ""}`);
        const collect = (tree: components["schemas"]["TaxonomyTreeNode"]): SubtopicOption[] => [
          ...(tree.level === "topic" || tree.level === "subtopic" ? [{ id: tree.id, name: tree.name, paperCode: tree.paper_id, chapterName: tree.breadcrumbs.map(value => value.name).join(" → "), topicName: "" }] : []),
          ...(tree.children ?? []).flatMap(collect),
        ];
        return trees.flatMap(collect);
      }
      const papers = requiredData(await curatorClient.GET("/api/v1/papers"));
      const trees = await Promise.all(papers.map(async paper => requiredData(await curatorClient.GET("/api/v1/tree", { params: { query: { paper: paper.id } } }))));
      const nodes: SubtopicOption[] = trees.flatMap(tree => tree.chapters.flatMap(chapter => chapter.topics.flatMap(topic => topic.subtopics.map(subtopic => ({ id: subtopic.id, name: subtopic.name, paperCode: tree.code, chapterName: chapter.name, topicName: topic.name })))));
      nodes.sort((a, b) => a.paperCode.localeCompare(b.paperCode) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
      return nodes;
    },
    enabled: isOpen && !candidates,
  });

  if (!isOpen) return null;

  const filtered = (candidates ?? allSubtopics).filter((n) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      n.name.toLowerCase().includes(q) ||
      n.id.toLowerCase().includes(q) ||
      n.paperCode.toLowerCase().includes(q) ||
      n.chapterName.toLowerCase().includes(q) || n.topicName.toLowerCase().includes(q)
    );
  });

  return (
    <dialog ref={dialogRef} onCancel={onClose} aria-label="Select Canonical Subtopic" className="review-dialog max-w-2xl w-full p-0">
      <div className="bg-slate-800 rounded-xl border border-slate-700 max-h-[80vh] flex flex-col overflow-hidden">
        {/* Modal Header */}
        <div className="p-4 border-b border-[#334155] flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-white">Select Canonical Subtopic</h3>
            <p className="text-[11px] text-slate-400">Search subtopics across returned papers</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close node picker"
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search input */}
        <div className="p-3 border-b border-[#334155] bg-slate-900/40">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by subtopic name, section number, chapter or node ID…"
              aria-label="Search topics"
              className="w-full pl-9 pr-3 py-2 rounded-xl text-sm bg-slate-900 border border-slate-700 placeholder:text-slate-500 focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Nodes List */}
        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/80 p-2 text-xs">
          <RequestError error={error} retry={() => void refetch()} />
          {isPending && !candidates ? <p role="status" className="p-8 text-center">Loading subtopics…</p> : error ? null : filtered.length === 0 ? (
            <div className="p-8 text-center text-slate-500">No matching subtopics found.</div>
          ) : (
            filtered.map((item) => {
              const isSelected = item.id === currentSelectedId;

              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    onSelect(item.id);
                    onClose();
                  }}
                  className={`w-full p-3 flex items-center justify-between text-left rounded-xl transition-colors ${
                    isSelected
                      ? "bg-indigo-950/80 border border-indigo-700 text-white"
                      : "hover:bg-slate-800/60 text-slate-200"
                  }`}
                >
                  <div className="space-y-0.5 truncate pr-3">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] font-bold px-1.5 py-0.2 rounded bg-slate-800 text-indigo-400">
                        {item.paperCode}
                      </span>
                      <span className="font-semibold text-xs text-white truncate">
                        {item.name}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-400 truncate">
                      {item.chapterName}{item.topicName && ` → ${item.topicName}`} · <span className="font-mono">{item.id}</span>
                    </div>
                  </div>

                  {isSelected && <Check className="w-4 h-4 text-indigo-400 shrink-0" />}
                </button>
              );
            })
          )}
        </div>
      </div>
    </dialog>
  );
}
