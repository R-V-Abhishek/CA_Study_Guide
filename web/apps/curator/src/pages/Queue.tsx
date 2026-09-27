import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { tinykeys } from "tinykeys";
import {
  Check,
  Edit2,
  XCircle,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  Filter,
} from "lucide-react";
import { NodePickerModal } from "../components/NodePickerModal";
import { curatorClient } from "../lib/client";

interface SuggestionItem {
  node_id: string;
  node_name: string;
  justification?: string | null;
  gist?: string | null;
  alternatives?: any[];
}

interface CuratorUnit {
  unit_id: number;
  document_id: number;
  attempt_id: string;
  paper_id: string;
  doc_type_id: string;
  label_path: string;
  display_label: string;
  marks: number | null;
  question_text: string;
  answer_text: string | null;
  bucket: string;
  primary_suggestion: SuggestionItem;
  secondary_suggestions: Array<{ node_id: string; node_name: string }>;
}

export function Queue() {
  const queryClient = useQueryClient();
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [bucketFilter, setBucketFilter] = useState<string>("all");
  const [paperFilter, setPaperFilter] = useState<string>("all");
  const [pickerOpen, setPickerOpen] = useState<boolean>(false);
  const startTimeRef = useRef<number>(Date.now());

  // Fetch pending review queue
  const { data: queueItems = [], isLoading } = useQuery({
    queryKey: ["curator-queue", bucketFilter, paperFilter],
    queryFn: async () => {
      try {
        const queryParams: Record<string, any> = {};
        if (bucketFilter !== "all") queryParams.bucket = bucketFilter;
        if (paperFilter !== "all") queryParams.paper_id = paperFilter;

        const res = await curatorClient.GET("/api/v1/curate/queue", {
          params: { query: queryParams },
        });
        if (res.data) {
          return res.data as CuratorUnit[];
        }
      } catch (err) {
        console.warn("Failed fetching curate queue:", err);
      }
      return [];
    },
  });

  const total = queueItems.length;
  const currentUnit = total > 0 && currentIndex < total ? queueItems[currentIndex] : null;

  // Reset timer whenever current unit changes
  useEffect(() => {
    startTimeRef.current = Date.now();
  }, [currentIndex, currentUnit?.unit_id]);

  // Decision mutation
  const decisionMutation = useMutation({
    mutationFn: async ({
      action,
      primaryNodeId,
    }: {
      action: string;
      primaryNodeId?: string;
    }) => {
      if (!currentUnit) return;
      const secondsSpent = Math.max(1, (Date.now() - startTimeRef.current) / 1000);

      const res = await curatorClient.POST("/api/v1/curate/units/{unit_id}/decision", {
        params: { path: { unit_id: currentUnit.unit_id } },
        body: {
          action,
          primary_node_id:
            primaryNodeId ||
            (action === "none_fits" || action === "exclude"
              ? null
              : currentUnit.primary_suggestion.node_id),
          secondary_node_ids: [],
          seconds_spent: secondsSpent,
          blind: false,
        },
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["curator-queue"] });
      // Advance to next unit
      if (currentIndex < total - 1) {
        setCurrentIndex((prev) => prev + 1);
      }
    },
  });

  // Action handlers
  const handleAccept = () => {
    if (!currentUnit || decisionMutation.isPending) return;
    decisionMutation.mutate({ action: "accept" });
  };

  const handleNoneFits = () => {
    if (!currentUnit || decisionMutation.isPending) return;
    decisionMutation.mutate({ action: "none_fits" });
  };

  const handleExclude = () => {
    if (!currentUnit || decisionMutation.isPending) return;
    decisionMutation.mutate({ action: "exclude" });
  };

  const handleCustomNodeSelected = (nodeId: string) => {
    if (!currentUnit) return;
    decisionMutation.mutate({ action: "edit", primaryNodeId: nodeId });
  };

  const handleNext = () => {
    if (currentIndex < total - 1) {
      setCurrentIndex((prev) => prev + 1);
    }
  };

  const handlePrev = () => {
    if (currentIndex > 0) {
      setCurrentIndex((prev) => prev - 1);
    }
  };

  // Bind keyboard shortcuts
  useEffect(() => {
    if (pickerOpen) return; // Do not trigger shortcuts when modal is open

    const unsubscribe = tinykeys(window, {
      a: (e) => {
        e.preventDefault();
        handleAccept();
      },
      e: (e) => {
        e.preventDefault();
        setPickerOpen(true);
      },
      n: (e) => {
        e.preventDefault();
        handleNoneFits();
      },
      x: (e) => {
        e.preventDefault();
        handleExclude();
      },
      ArrowRight: (e) => {
        e.preventDefault();
        handleNext();
      },
      l: (e) => {
        e.preventDefault();
        handleNext();
      },
      ArrowLeft: (e) => {
        e.preventDefault();
        handlePrev();
      },
      h: (e) => {
        e.preventDefault();
        handlePrev();
      },
    });

    return () => unsubscribe();
  }, [currentUnit, currentIndex, total, pickerOpen]);

  if (isLoading && total === 0) {
    return (
      <div className="p-12 text-center text-slate-400 space-y-3">
        <div className="h-6 w-48 bg-slate-800 rounded animate-pulse mx-auto" />
        <div className="h-64 w-full bg-slate-800 rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (total === 0 || !currentUnit) {
    return (
      <div className="p-12 text-center bg-[#1E293B] rounded-2xl border border-[#334155] space-y-4 max-w-xl mx-auto my-12">
        <div className="w-12 h-12 rounded-full bg-emerald-950 border border-emerald-700 text-emerald-400 flex items-center justify-center mx-auto text-xl font-bold">
          ✓
        </div>
        <h2 className="text-lg font-bold text-white">Queue Empty</h2>
        <p className="text-xs text-slate-400 leading-relaxed">
          All gradable exam units have been reviewed or no pending units match the selected filters.
        </p>
      </div>
    );
  }

  const prim = currentUnit.primary_suggestion;
  const isBucketA = currentUnit.bucket === "A";

  return (
    <div className="space-y-4 animate-in fade-in duration-150">
      {/* Top Filter and Navigation Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#334155]">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
            <Filter className="w-3.5 h-3.5" />
            <span>Filter:</span>
          </div>

          <select
            value={bucketFilter}
            onChange={(e) => {
              setBucketFilter(e.target.value);
              setCurrentIndex(0);
            }}
            className="px-2.5 py-1 rounded-lg text-xs bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="all">All Buckets</option>
            <option value="A">Bucket A (High Confidence)</option>
            <option value="B">Bucket B (Ambiguous)</option>
            <option value="C">Bucket C (Low Signal)</option>
          </select>

          <select
            value={paperFilter}
            onChange={(e) => {
              setPaperFilter(e.target.value);
              setCurrentIndex(0);
            }}
            className="px-2.5 py-1 rounded-lg text-xs bg-slate-900 border border-slate-700 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="all">All Papers</option>
            <option value="s2023.P1">P1 — FR</option>
            <option value="s2023.P2">P2 — AFM</option>
            <option value="s2023.P3">P3 — Audit</option>
            <option value="s2023.P4">P4 — DT</option>
            <option value="s2023.P5">P5 — IDT</option>
            <option value="s2023.P6">P6 — IBS</option>
          </select>
        </div>

        {/* Unit pagination controls */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handlePrev}
            disabled={currentIndex === 0}
            className="p-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Previous Unit [H / ←]"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <span className="font-mono text-xs font-semibold px-2 text-slate-300">
            {currentIndex + 1} / {total}
          </span>

          <button
            type="button"
            onClick={handleNext}
            disabled={currentIndex >= total - 1}
            className="p-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Next Unit [L / →]"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Split Grid: Left = Unit Q&A, Right = Suggestion & Decision Bar */}
      <div className="grid grid-cols-12 gap-5 min-h-[550px]">
        {/* Left 8 Columns: Question & Answer Preview */}
        <div className="col-span-12 lg:col-span-8 p-6 rounded-2xl bg-[#1E293B] border border-[#334155] space-y-5 flex flex-col justify-between">
          <div className="space-y-4">
            {/* Unit Meta Header */}
            <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-xs px-2 py-0.5 rounded bg-indigo-950 border border-indigo-700 text-indigo-300 font-bold">
                  Unit #{currentUnit.unit_id}
                </span>
                <span className="text-xs font-semibold text-white">
                  {currentUnit.paper_id} · {currentUnit.attempt_id} · {currentUnit.display_label}
                </span>
                <span className="font-mono text-[11px] text-slate-400">
                  ({currentUnit.label_path})
                </span>
              </div>

              {currentUnit.marks != null && (
                <span className="font-mono text-xs font-bold text-amber-400 px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800/80">
                  {currentUnit.marks} Marks
                </span>
              )}
            </div>

            {/* Question Text Box */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Question Text
              </div>
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs font-mono leading-relaxed text-slate-200 whitespace-pre-wrap max-h-60 overflow-y-auto">
                {currentUnit.question_text || "(No question text parsed)"}
              </div>
            </div>

            {/* Answer Text Box */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Model Solution / Answer
              </div>
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs font-mono leading-relaxed text-slate-300 whitespace-pre-wrap max-h-60 overflow-y-auto">
                {currentUnit.answer_text || "(No paired answer text found in document)"}
              </div>
            </div>
          </div>

          {/* Quick keyboard reminder footer */}
          <div className="text-[11px] text-slate-400 font-mono pt-3 border-t border-slate-800 flex items-center justify-between">
            <span>Press <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-200">A</kbd> to accept</span>
            <span>Press <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-200">E</kbd> to edit</span>
            <span>Press <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-200">N</kbd> for none fits</span>
            <span>Press <kbd className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-200">X</kbd> to exclude</span>
          </div>
        </div>

        {/* Right 4 Columns: Classification Suggestion & Action Controls */}
        <div className="col-span-12 lg:col-span-4 space-y-4 flex flex-col justify-between">
          <div className="p-5 rounded-2xl bg-[#1E293B] border border-[#334155] space-y-4">
            <div className="flex items-center justify-between border-b border-slate-700/60 pb-2.5">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Classifier Recommendation
              </span>
              <span
                className={`font-mono text-xs font-bold px-2 py-0.5 rounded border ${
                  isBucketA
                    ? "bg-emerald-950 border-emerald-700 text-emerald-400"
                    : "bg-amber-950 border-amber-700 text-amber-400"
                }`}
              >
                Bucket {currentUnit.bucket}
              </span>
            </div>

            {/* Primary Node Suggestion Card */}
            <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-emerald-400">Primary Subtopic</span>
                <span className="font-mono text-[10px] text-slate-400">Consensus match</span>
              </div>

              <div className="font-mono text-xs text-indigo-400 font-bold">
                {prim?.node_id}
              </div>
              <div className="text-xs font-semibold text-white">
                {prim?.node_name}
              </div>

              {prim?.justification && (
                <div className="text-[11px] text-slate-400 pt-2 border-t border-slate-800 leading-relaxed font-mono">
                  {prim.justification}
                </div>
              )}
            </div>

            {/* Secondary Suggestions if present */}
            {currentUnit.secondary_suggestions && currentUnit.secondary_suggestions.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Alternative Candidates
                </div>
                <div className="space-y-1">
                  {currentUnit.secondary_suggestions.map((sec) => (
                    <button
                      key={sec.node_id}
                      type="button"
                      onClick={() => handleCustomNodeSelected(sec.node_id)}
                      className="w-full p-2.5 rounded-lg bg-slate-900/60 hover:bg-slate-800 border border-slate-800/80 text-left transition-colors flex items-center justify-between text-xs group"
                    >
                      <div className="truncate pr-2">
                        <span className="font-mono font-bold text-slate-400 group-hover:text-indigo-400 mr-2">
                          {sec.node_id}
                        </span>
                        <span className="text-slate-300">{sec.node_name}</span>
                      </div>
                      <span className="text-[10px] font-semibold text-indigo-400 shrink-0">
                        Pick →
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Action Buttons Panel */}
          <div className="p-5 rounded-2xl bg-[#1E293B] border border-[#334155] space-y-2.5">
            <button
              type="button"
              onClick={handleAccept}
              disabled={decisionMutation.isPending}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 font-bold text-xs text-white transition-colors shadow-sm cursor-pointer disabled:opacity-50"
            >
              <Check className="w-4 h-4" />
              <span>[A] Accept Recommendation</span>
            </button>

            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              disabled={decisionMutation.isPending}
              className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 font-semibold text-xs text-slate-200 transition-colors cursor-pointer"
            >
              <Edit2 className="w-3.5 h-3.5 text-indigo-400" />
              <span>[E] Reclassify (Choose Node)</span>
            </button>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <button
                type="button"
                onClick={handleNoneFits}
                disabled={decisionMutation.isPending}
                className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] font-medium text-slate-300 transition-colors cursor-pointer"
              >
                <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                <span>[N] None Fits</span>
              </button>

              <button
                type="button"
                onClick={handleExclude}
                disabled={decisionMutation.isPending}
                className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] font-medium text-rose-400 transition-colors cursor-pointer"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>[X] Exclude</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Node Picker Modal */}
      <NodePickerModal
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={handleCustomNodeSelected}
        currentSelectedId={prim?.node_id}
      />
    </div>
  );
}
