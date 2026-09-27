import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import confetti from "canvas-confetti";
import {
  ArrowLeft,
  Check,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  FileText,
  Calendar,
} from "lucide-react";
import { ImportanceDots } from "../components/ImportanceDots";
import { isDemoMode } from "../lib/demo";
import { client } from "../lib/client";
import demoRevision from "../fixtures/revision.json";

interface RevisionItem {
  node_id: string;
  node_name: string;
  paper_id?: string;
  paper_code: string;
  chapter_name?: string;
  topic_name?: string;
  importance: number;
  due_date?: string;
  days_overdue?: number;
  interval_days?: number;
  interval_stage?: number;
  last_revised_at?: string | null;
  notes_preview?: string | null;
}

interface RevisionDueResponse {
  total_due: number;
  items: RevisionItem[];
  upcoming_7d_count?: number;
}

export function Revision() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [notesExpanded, setNotesExpanded] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<"ok" | "shaky" | null>(null);

  // Fetch due revisions
  const { data: apiData, isLoading } = useQuery({
    queryKey: ["revision-due"],
    queryFn: async () => {
      if (isDemoMode()) {
        return null;
      }
      try {
        const res = await client.GET("/api/v1/revision/due");
        if (res.data) {
          return res.data as unknown as RevisionDueResponse;
        }
      } catch (err) {
        console.warn("Failed fetching live revision queue, falling back to demo:", err);
      }
      return null;
    },
  });

  // Blend with demo data if empty or offline
  const dueItems: RevisionItem[] = (apiData?.items && apiData.items.length > 0)
    ? apiData.items
    : (demoRevision as any[]).map((dr) => ({
        node_id: dr.node_id,
        node_name: dr.subtopic_name,
        paper_code: dr.paper_code,
        chapter_name: "Financial Reporting Standards",
        importance: dr.importance,
        days_overdue: dr.days_overdue,
        interval_days: dr.interval_days,
        interval_stage: dr.interval_stage,
        notes_preview:
          dr.node_id === "P1-EQ3KR1"
            ? "Lessee accounting: recognize Right-of-Use (ROU) asset and lease liability on commencement date. Exemption applies for short-term (<12m) and low-value assets."
            : "Review key measurement guidelines, disclosures, and retrospective application rules.",
      }));

  const totalDue = dueItems.length;
  const isFinished = totalDue === 0 || currentIndex >= totalDue;
  const currentCard = !isFinished ? dueItems[currentIndex] : null;

  // Outcome mutation
  const outcomeMutation = useMutation({
    mutationFn: async ({ nodeId, outcome }: { nodeId: string; outcome: "ok" | "shaky" }) => {
      const res = await client.POST("/api/v1/subtopics/{node_id}/revisions", {
        params: { path: { node_id: nodeId } },
        body: { outcome },
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["revision-due"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const handleDecision = (outcome: "ok" | "shaky") => {
    if (!currentCard || feedback) return;

    setFeedback(outcome);
    outcomeMutation.mutate({ nodeId: currentCard.node_id, outcome });

    if (outcome === "ok") {
      confetti({
        particleCount: 40,
        spread: 45,
        origin: { y: 0.6 },
        colors: ["#10B981", "#4F46E5", "#F59E0B"],
      });
    }

    // Pause 400ms so choice registers visually before advancing
    setTimeout(() => {
      setFeedback(null);
      setNotesExpanded(false);
      setCurrentIndex((prev) => prev + 1);

      if (currentIndex + 1 >= totalDue) {
        confetti({
          particleCount: 100,
          spread: 80,
          origin: { y: 0.5 },
          colors: ["#4F46E5", "#10B981", "#F59E0B", "#EC4899"],
        });
      }
    }, 400);
  };

  if (isLoading && totalDue === 0) {
    return (
      <div className="max-w-2xl mx-auto py-16 text-center space-y-4">
        <div className="h-6 w-48 bg-stone-200 dark:bg-stone-800 rounded animate-pulse mx-auto" />
        <div className="h-64 w-full bg-stone-200 dark:bg-stone-800 rounded-3xl animate-pulse" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Top Navbar */}
      <div className="flex items-center justify-between pb-2 border-b border-stone-200 dark:border-stone-800">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back</span>
        </button>

        <div className="flex items-center gap-2">
          <RotateCcw className="w-4 h-4 text-orange-600 dark:text-orange-400" />
          <h1 className="font-bold text-sm text-stone-900 dark:text-white">
            Revision Queue
          </h1>
        </div>

        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-orange-50 dark:bg-orange-950/60 text-orange-700 dark:text-orange-300">
          {!isFinished ? `${currentIndex + 1} of ${totalDue} due today` : "Done"}
        </span>
      </div>

      {/* Finished Celebration View */}
      {isFinished ? (
        <div className="p-12 text-center bg-white dark:bg-stone-900 rounded-3xl border border-stone-200 dark:border-stone-800 shadow-sm space-y-6 animate-in zoom-in-95 duration-300">
          <div className="w-16 h-16 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto text-2xl">
            🎉
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-black text-stone-900 dark:text-white tracking-tight">
              All caught up for today!
            </h2>
            <p className="text-xs md:text-sm text-stone-500 max-w-md mx-auto leading-relaxed">
              You've cleared your spaced repetition queue. Consistent recall reviews protect against the forgetting curve.
            </p>
          </div>

          <div className="pt-2 flex justify-center gap-3">
            <Link
              to="/"
              className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs transition-colors shadow-sm"
            >
              Return to Dashboard
            </Link>
            <Link
              to="/plan"
              className="px-5 py-2.5 rounded-xl bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 text-stone-800 dark:text-stone-200 font-semibold text-xs transition-colors"
            >
              Check Study Plan
            </Link>
          </div>
        </div>
      ) : (
        /* The Focused Anki-Style Card */
        <div className="space-y-6">
          <div
            className={`p-8 md:p-10 rounded-3xl bg-white dark:bg-stone-900 border ${
              feedback === "ok"
                ? "border-emerald-500 ring-2 ring-emerald-500/20 shadow-emerald-500/10"
                : feedback === "shaky"
                ? "border-amber-500 ring-2 ring-amber-500/20 shadow-amber-500/10"
                : "border-stone-200/90 dark:border-stone-800"
            } shadow-md transition-all duration-300 space-y-8`}
          >
            {/* Card Header: Context */}
            <div className="space-y-2 border-b border-stone-100 dark:border-stone-800/80 pb-4">
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold text-xs px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/70 text-indigo-600 dark:text-indigo-400">
                  {currentCard?.paper_code}
                </span>
                <ImportanceDots score={currentCard?.importance ?? 0.8} size="md" />
              </div>
              <div className="text-xs text-stone-400 font-medium">
                {currentCard?.chapter_name || "CA Final Core Syllabus"}
              </div>
            </div>

            {/* Prompt / Title */}
            <div className="space-y-3">
              <h2 className="text-xl md:text-2xl font-bold tracking-tight text-stone-900 dark:text-stone-100 leading-snug">
                {currentCard?.node_name}
              </h2>
              <div className="flex items-center gap-3 text-xs text-stone-500">
                <span>
                  Interval: <strong>{currentCard?.interval_days || 7} days</strong> (Stage{" "}
                  {currentCard?.interval_stage || 2} of 4)
                </span>
                {currentCard?.days_overdue && currentCard.days_overdue > 0 && (
                  <span className="text-amber-600 dark:text-amber-400 font-medium">
                    · Overdue by {currentCard.days_overdue} days
                  </span>
                )}
              </div>
            </div>

            {/* Expandable Notes Preview */}
            <div className="rounded-2xl border border-stone-200/80 dark:border-stone-800 bg-stone-50/70 dark:bg-stone-800/40 overflow-hidden">
              <button
                type="button"
                onClick={() => setNotesExpanded(!notesExpanded)}
                className="w-full p-4 flex items-center justify-between text-left hover:bg-stone-100/60 dark:hover:bg-stone-800/80 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-stone-400" />
                  <span className="text-xs font-bold text-stone-700 dark:text-stone-300">
                    Your key notes & formulas
                  </span>
                </div>
                <div className="flex items-center gap-1 text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                  <span>{notesExpanded ? "Collapse" : "Tap to reveal notes"}</span>
                  {notesExpanded ? (
                    <ChevronUp className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5" />
                  )}
                </div>
              </button>

              {notesExpanded && (
                <div className="p-4 pt-1 text-xs text-stone-700 dark:text-stone-300 leading-relaxed border-t border-stone-100 dark:border-stone-800 font-mono bg-white dark:bg-stone-900/60">
                  {currentCard?.notes_preview ||
                    "No personal notes recorded yet. You can add formulas and summaries in the subtopic study view."}
                </div>
              )}
            </div>

            {/* Prompt & Decision Buttons */}
            <div className="space-y-4 pt-2">
              <div className="text-center text-xs uppercase font-bold tracking-wider text-stone-400">
                How well do you remember this?
              </div>

              <div className="grid grid-cols-2 gap-4">
                <button
                  type="button"
                  onClick={() => handleDecision("ok")}
                  disabled={feedback !== null}
                  className={`flex flex-col items-center justify-center p-4 rounded-2xl font-bold text-xs transition-all shadow-sm ${
                    feedback === "ok"
                      ? "bg-emerald-600 text-white scale-[1.02]"
                      : "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/50 hover:bg-emerald-600 hover:text-white"
                  }`}
                >
                  <Check className="w-5 h-5 mb-1" />
                  <span>✓ Got It — Advance Interval</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleDecision("shaky")}
                  disabled={feedback !== null}
                  className={`flex flex-col items-center justify-center p-4 rounded-2xl font-bold text-xs transition-all shadow-sm ${
                    feedback === "shaky"
                      ? "bg-amber-600 text-white scale-[1.02]"
                      : "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-900/50 hover:bg-amber-600 hover:text-white"
                  }`}
                >
                  <RotateCcw className="w-5 h-5 mb-1" />
                  <span>≈ Shaky — Reset Interval</span>
                </button>
              </div>
            </div>
          </div>

          {/* Upcoming Info Tile */}
          <div className="p-4 rounded-2xl bg-stone-50 dark:bg-stone-900/40 border border-stone-200 dark:border-stone-800 flex items-center justify-between text-xs text-stone-500">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-stone-400" />
              <span>Upcoming revisions (next 7 days): <strong>12 topics</strong></span>
            </div>
            <Link
              to={`/papers/${currentCard?.paper_code}/${currentCard?.node_id}`}
              className="text-indigo-600 dark:text-indigo-400 font-semibold hover:underline"
            >
              Open in Syllabus Tree →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
