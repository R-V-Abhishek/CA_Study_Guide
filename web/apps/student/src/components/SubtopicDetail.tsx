import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import confetti from "canvas-confetti";
import {
  CheckCircle2,
  Circle,
  Clock,
  Flag,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  FileText,
  Sparkles,
  Save,
  Calendar,
} from "lucide-react";
import { ImportanceDots, getImportanceLabel } from "./ImportanceDots";
import { client } from "../lib/client";

export interface SubtopicAppearance {
  id: number;
  attempt_id: string;
  signal_class: "exam" | "practice";
  display_label: string;
  marks: number | null;
  gist?: string;
  official_url?: string;
  page_start?: number;
  page_end?: number;
  law_stale: boolean;
}

export interface SubtopicScoreData {
  importance: number;
  exam_score: number;
  practice_score: number;
  weight_prior: number;
  freq_hits: number;
  freq_window: number;
  exam_marks_total: number;
  exam_count: number;
  practice_count: number;
  first_exam_attempt?: string | null;
  last_exam_attempt?: string | null;
  weak: boolean;
  applicable: boolean;
}

export interface SubtopicData {
  id: string;
  name: string;
  paper?: { id: string; code: string; name: string } | null;
  chapter?: { id: string; name: string } | null;
  topic?: { id: string; name: string } | null;
  status: "not_started" | "in_progress" | "done";
  notes?: string | null;
  status_changed_at?: string | null;
  first_done_at?: string | null;
  last_revised_at?: string | null;
  weightage?: { section_name?: string; min_pct: number; max_pct: number } | null;
  score?: SubtopicScoreData;
  appearances: SubtopicAppearance[];
}

export interface WhyData {
  node_id?: string;
  paper_code?: string;
  subtopic_name?: string;
  importance?: number;
  summary?: string;
  drivers?: Array<{ name: string; score: number; contribution_pct: number; explanation: string }>;
}

export interface SubtopicDetailProps {
  paperId: string;
  nodeId: string;
  onStatusChange?: (newStatus: "not_started" | "in_progress" | "done") => void;
}

export function SubtopicDetail({ paperId, nodeId, onStatusChange }: SubtopicDetailProps) {
  const queryClient = useQueryClient();
  const [whyExpanded, setWhyExpanded] = useState(false);
  const [notesText, setNotesText] = useState("");
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");

  // Fetch subtopic details
  const { data: subtopic, isLoading } = useQuery({
    queryKey: ["subtopic", nodeId],
    queryFn: async () => {
      try {
        const res = await client.GET("/api/v1/subtopics/{node_id}", {
          params: { path: { node_id: nodeId } },
        });
        if (res.data) {
          return res.data as unknown as SubtopicData;
        }
      } catch (err) {
        console.warn("Failed fetching subtopic:", err);
      }
      return null;
    },
  });

  // Fetch why explanation
  const { data: whyData } = useQuery({
    queryKey: ["why", nodeId],
    queryFn: async () => {
      try {
        const res = await client.GET("/api/v1/why/subtopic/{node_id}", {
          params: { path: { node_id: nodeId } },
        });
        if (res.data) {
          return res.data as unknown as WhyData;
        }
      } catch (err) {
        console.warn("Failed fetching why data:", err);
      }
      return null;
    },
  });

  // Sync notes text when subtopic loads
  useEffect(() => {
    if (subtopic?.notes !== undefined) {
      setNotesText(subtopic.notes || "");
      setSaveStatus("saved");
    }
  }, [subtopic?.notes]);

  // Mutation for updating status with optimistic updates and celebratory confetti
  const statusMutation = useMutation({
    mutationFn: async (newStatus: "not_started" | "in_progress" | "done") => {
      const res = await client.PUT("/api/v1/subtopics/{node_id}/progress", {
        params: { path: { node_id: nodeId } },
        body: { status: newStatus },
      });
      return res.data;
    },
    onMutate: async (newStatus) => {
      // Optimistic update
      await queryClient.cancelQueries({ queryKey: ["subtopic", nodeId] });
      const previous = queryClient.getQueryData(["subtopic", nodeId]);

      queryClient.setQueryData(["subtopic", nodeId], (old: SubtopicData | null) => {
        if (!old) return old;
        return {
          ...old,
          status: newStatus,
        };
      });

      if (onStatusChange) {
        onStatusChange(newStatus);
      }

      if (newStatus === "done") {
        confetti({
          particleCount: 80,
          spread: 60,
          origin: { y: 0.7 },
          colors: ["#4F46E5", "#10B981", "#F59E0B", "#EC4899"],
        });
      }

      return { previous };
    },
    onError: (_err, _newStatus, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["subtopic", nodeId], context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["subtopic", nodeId] });
      queryClient.invalidateQueries({ queryKey: ["paper-tree", paperId] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["papers"] });
    },
  });

  // Auto-save notes mutation with debounce
  const notesMutation = useMutation({
    mutationFn: async (text: string) => {
      const res = await client.PUT("/api/v1/subtopics/{node_id}/notes", {
        params: { path: { node_id: nodeId } },
        body: { notes: text },
      });
      return res.data;
    },
    onSuccess: () => {
      setSaveStatus("saved");
    },
  });

  const handleNotesChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setNotesText(val);
    setSaveStatus("unsaved");
  };

  const handleSaveNotes = () => {
    setSaveStatus("saving");
    notesMutation.mutate(notesText);
  };

  if (isLoading && !subtopic) {
    return (
      <div className="p-8 space-y-4">
        <div className="h-4 w-48 bg-stone-200 dark:bg-stone-800 rounded animate-pulse" />
        <div className="h-8 w-3/4 bg-stone-200 dark:bg-stone-800 rounded animate-pulse" />
        <div className="h-24 w-full bg-stone-200 dark:bg-stone-800 rounded-xl animate-pulse" />
      </div>
    );
  }

  const currentStatus = subtopic?.status || "not_started";
  const importanceScore = subtopic?.score?.importance ?? 0.75;
  const impBadge = getImportanceLabel(importanceScore);
  const freqHits = subtopic?.score?.freq_hits ?? 0;
  const freqWindow = subtopic?.score?.freq_window ?? 0;
  const isWeak = subtopic?.score?.weak || false;
  const examMarksTotal = subtopic?.score?.exam_marks_total ?? 0;
  const appearances = subtopic?.appearances || [];

  return (
    <div className="p-6 md:p-8 space-y-6 max-w-4xl">
      {/* Breadcrumbs */}
      <div className="flex items-center gap-1.5 text-xs text-stone-500 font-medium flex-wrap">
        <span className="font-bold text-indigo-600 dark:text-indigo-400">
          {subtopic?.paper?.code || paperId}
        </span>
        <span>›</span>
        <span>{subtopic?.chapter?.name || "Chapter"}</span>
        <span>›</span>
        <span className="text-stone-800 dark:text-stone-200">{subtopic?.topic?.name || "Topic"}</span>
      </div>

      {/* Title & Importance Header */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h1 className="text-xl md:text-2xl font-bold tracking-tight text-stone-900 dark:text-stone-100">
            {subtopic?.name || "Subtopic Details"}
          </h1>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <ImportanceDots score={importanceScore} size="lg" />
          <span
            className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${impBadge.bg} ${impBadge.color}`}
          >
            {impBadge.label}
          </span>
          {freqHits > 0 && (
            <span className="text-xs text-stone-500 font-medium">
              Asked in {freqHits} of last {freqWindow || 8} exams
              {examMarksTotal > 0 && ` (${Math.round(examMarksTotal / freqHits)} marks typical)`}
            </span>
          )}
        </div>
      </div>

      {/* 3-Segment Status Toggle Button Bar */}
      <div className="p-4 rounded-2xl bg-stone-50 dark:bg-stone-900/60 border border-stone-200 dark:border-stone-800 space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-stone-500">
          <span className="uppercase tracking-wider">STUDY STATUS</span>
          {subtopic?.last_revised_at && (
            <span>Last revised: {new Date(subtopic.last_revised_at).toLocaleDateString()}</span>
          )}
        </div>

        <div className="grid grid-cols-3 gap-2 p-1 rounded-xl bg-white dark:bg-stone-800/80 border border-stone-200/80 dark:border-stone-700/80">
          <button
            type="button"
            onClick={() => statusMutation.mutate("not_started")}
            className={`flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-lg text-xs font-bold transition-all ${
              currentStatus === "not_started"
                ? "bg-stone-100 dark:bg-stone-700 text-stone-900 dark:text-white shadow-sm"
                : "text-stone-500 hover:text-stone-800 dark:hover:text-stone-300"
            }`}
          >
            <Circle className="w-3.5 h-3.5 text-stone-400" />
            <span>Not Started</span>
          </button>

          <button
            type="button"
            onClick={() => statusMutation.mutate("in_progress")}
            className={`flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-lg text-xs font-bold transition-all ${
              currentStatus === "in_progress"
                ? "bg-amber-500 text-white shadow-sm"
                : "text-stone-500 hover:text-stone-800 dark:hover:text-stone-300"
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>In Progress</span>
          </button>

          <button
            type="button"
            onClick={() => statusMutation.mutate("done")}
            className={`flex items-center justify-center gap-1.5 py-2.5 px-3 rounded-lg text-xs font-bold transition-all ${
              currentStatus === "done"
                ? "bg-emerald-600 text-white shadow-sm"
                : "text-stone-500 hover:text-stone-800 dark:hover:text-stone-300"
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Done ✓</span>
          </button>
        </div>
      </div>

      {/* Weak Flag Alert (if applicable) */}
      {isWeak && (
        <div className="p-4 rounded-xl bg-orange-50/70 dark:bg-orange-950/30 border-l-4 border-orange-500 dark:border-orange-500 border-r border-t border-b border-orange-200 dark:border-orange-900/50 flex items-start gap-3">
          <Flag className="w-5 h-5 text-orange-600 dark:text-orange-400 shrink-0 mt-0.5 fill-orange-500" />
          <div className="space-y-1">
            <h4 className="text-xs font-bold uppercase tracking-wider text-orange-900 dark:text-orange-300">
              WEAK COVERAGE ALERT
            </h4>
            <p className="text-xs text-orange-800 dark:text-orange-200">
              This subtopic appeared in {freqHits} of the last {freqWindow} exams, but is currently not marked Done. Prioritize studying this before the upcoming attempt.
            </p>
          </div>
        </div>
      )}

      {/* WHY IS THIS IMPORTANT? Accordion */}
      <div className="rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 overflow-hidden shadow-sm">
        <button
          type="button"
          onClick={() => setWhyExpanded(!whyExpanded)}
          className="w-full p-4 flex items-center justify-between text-left hover:bg-stone-50 dark:hover:bg-stone-800/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            <span className="text-xs font-bold uppercase tracking-wider text-stone-800 dark:text-stone-200">
              WHY IS THIS IMPORTANT?
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs font-semibold text-indigo-600 dark:text-indigo-400">
            <span>{whyExpanded ? "Hide breakdown" : "See math breakdown"}</span>
            {whyExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </button>

        <div className="px-5 pb-5 space-y-4">
          <p className="text-xs md:text-sm text-stone-700 dark:text-stone-300 leading-relaxed">
            {whyData?.summary ||
              `Exam frequency: ${freqHits} hits in the last ${freqWindow} attempts. Chapter weightage section contributes significant marks in ICAI papers.`}
          </p>

          {/* Expanded E/P/W/I Math Breakdown */}
          {whyExpanded && (
            <div className="p-4 rounded-xl bg-stone-50 dark:bg-stone-800/60 border border-stone-200 dark:border-stone-700/60 space-y-3 animate-in fade-in duration-200">
              <div className="text-xs font-bold uppercase tracking-wider text-stone-500">
                Score Drivers (I = 0.50·E + 0.30·P + 0.20·W)
              </div>

              <div className="space-y-2 text-xs">
                {/* Exam Frequency Score (E) */}
                <div>
                  <div className="flex justify-between font-medium mb-1">
                    <span>Exam Score (E = 50% weight)</span>
                    <span className="font-mono font-bold">
                      {Math.round((subtopic?.score?.exam_score ?? 0.8) * 100)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-stone-200 dark:bg-stone-700 overflow-hidden">
                    <div
                      className="h-full bg-indigo-600 rounded-full"
                      style={{ width: `${(subtopic?.score?.exam_score ?? 0.8) * 100}%` }}
                    />
                  </div>
                </div>

                {/* Practice Frequency Score (P) */}
                <div>
                  <div className="flex justify-between font-medium mb-1">
                    <span>Practice Signal (P = 30% weight)</span>
                    <span className="font-mono font-bold">
                      {Math.round((subtopic?.score?.practice_score ?? 0.7) * 100)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-stone-200 dark:bg-stone-700 overflow-hidden">
                    <div
                      className="h-full bg-amber-500 rounded-full"
                      style={{ width: `${(subtopic?.score?.practice_score ?? 0.7) * 100}%` }}
                    />
                  </div>
                </div>

                {/* Weightage Prior Score (W) */}
                <div>
                  <div className="flex justify-between font-medium mb-1">
                    <span>Chapter Weightage Prior (W = 20% weight)</span>
                    <span className="font-mono font-bold">
                      {Math.round((subtopic?.score?.weight_prior ?? 0.15) * 100)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-stone-200 dark:bg-stone-700 overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 rounded-full"
                      style={{ width: `${Math.min(100, (subtopic?.score?.weight_prior ?? 0.15) * 300)}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* PAST EXAM & PRACTICE APPEARANCES (Decision D2 compliant: no question text or answer text) */}
      <div className="rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-stone-500" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-stone-800 dark:text-stone-200">
              PAST EXAM & PRACTICE APPEARANCES ({appearances.length} Total)
            </h3>
          </div>
          <span className="text-[10px] text-stone-400 font-medium">
            Verified ICAI Suggested Answers & RTPs
          </span>
        </div>

        {appearances.length === 0 ? (
          <p className="text-xs text-stone-500 py-3 text-center">
            No published appearances catalogued for this subtopic yet.
          </p>
        ) : (
          <div className="space-y-2">
            {appearances.map((app) => (
              <div
                key={app.id}
                className="flex items-center justify-between p-3 rounded-xl bg-stone-50 dark:bg-stone-800/50 border border-stone-200/70 dark:border-stone-700/60 text-xs"
              >
                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-stone-900 dark:text-stone-100">
                    {app.attempt_id}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      app.signal_class === "practice"
                        ? "bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300"
                        : "bg-indigo-100 dark:bg-indigo-950/60 text-indigo-800 dark:text-indigo-300"
                    }`}
                  >
                    {app.signal_class || "Exam"}
                  </span>
                  <span className="font-semibold text-stone-700 dark:text-stone-300">
                    {app.display_label}
                  </span>
                  {app.law_stale && (
                    <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-400">
                      <AlertTriangle className="w-3 h-3" />
                      <span>Stale Law</span>
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3">
                  {app.marks != null && (
                    <span className="font-bold text-stone-900 dark:text-stone-100">
                      {app.marks} marks
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* QUICK NOTES (Auto-saved) */}
      <div className="rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 p-5 space-y-3 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-stone-500" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-stone-800 dark:text-stone-200">
              STUDY NOTES
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {saveStatus === "unsaved" && (
              <button
                type="button"
                onClick={handleSaveNotes}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white transition-colors"
              >
                <Save className="w-3 h-3" />
                <span>Save</span>
              </button>
            )}
            <span className="text-[11px] text-stone-400">
              {saveStatus === "saving"
                ? "Saving…"
                : saveStatus === "saved"
                ? "Auto-saved"
                : "Unsaved changes"}
            </span>
          </div>
        </div>

        <textarea
          value={notesText}
          onChange={handleNotesChange}
          onBlur={handleSaveNotes}
          placeholder="Record key concepts, formulas, section numbers, or memory hooks for this subtopic…"
          rows={4}
          className="w-full p-3 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-800/40 text-xs md:text-sm text-stone-900 dark:text-stone-100 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
        />
      </div>
    </div>
  );
}
