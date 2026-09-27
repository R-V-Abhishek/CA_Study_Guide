import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, X, Check } from "lucide-react";
import { curatorClient } from "../lib/client";

interface SubtopicOption {
  id: string;
  name: string;
  paperCode: string;
  chapterName: string;
}

interface NodePickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (nodeId: string) => void;
  currentSelectedId?: string | null;
}

export function NodePickerModal({
  isOpen,
  onClose,
  onSelect,
  currentSelectedId,
}: NodePickerModalProps) {
  const [search, setSearch] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setSearch("");
    }
  }, [isOpen]);

  // Query all subtopics across papers
  const { data: allSubtopics = [] } = useQuery({
    queryKey: ["curator-all-nodes"],
    queryFn: async () => {
      const papers = ["P1", "P2", "P3", "P4", "P5", "P6"];
      const nodes: SubtopicOption[] = [];

      for (const p of papers) {
        try {
          const res = await curatorClient.GET("/api/v1/tree", {
            params: { query: { paper: p } },
          });
          if (res.data) {
            const tree: any = res.data;
            (tree.chapters || []).forEach((ch: any) => {
              (ch.topics || []).forEach((top: any) => {
                (top.subtopics || []).forEach((s: any) => {
                  nodes.push({
                    id: s.id,
                    name: s.name,
                    paperCode: tree.code || p,
                    chapterName: ch.name,
                  });
                });
              });
            });
          }
        } catch (err) {
          console.warn(`Failed loading nodes for ${p}:`, err);
        }
      }
      return nodes;
    },
    enabled: isOpen,
  });

  if (!isOpen) return null;

  const filtered = allSubtopics.filter((n) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      n.name.toLowerCase().includes(q) ||
      n.id.toLowerCase().includes(q) ||
      n.paperCode.toLowerCase().includes(q) ||
      n.chapterName.toLowerCase().includes(q)
    );
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-[#1E293B] rounded-2xl border border-[#334155] shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col overflow-hidden text-slate-100">
        {/* Modal Header */}
        <div className="p-4 border-b border-[#334155] flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-white">Select Canonical Subtopic</h3>
            <p className="text-[11px] text-slate-400">Search 264 syllabus nodes across all 6 papers</p>
          </div>
          <button
            type="button"
            onClick={onClose}
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
              className="w-full pl-9 pr-3 py-2 rounded-xl text-xs bg-slate-900 border border-slate-700 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Nodes List */}
        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/80 p-2 text-xs">
          {filtered.length === 0 ? (
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
                      {item.chapterName} · <span className="font-mono">{item.id}</span>
                    </div>
                  </div>

                  {isSelected && <Check className="w-4 h-4 text-indigo-400 shrink-0" />}
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
