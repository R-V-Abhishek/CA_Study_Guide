import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Calendar,
  Clock,
  ArrowRight,
  RotateCw,
  ChevronDown,
  CheckCircle2,
} from "lucide-react";
import { ImportanceDots } from "../components/ImportanceDots";
import { isDemoMode } from "../lib/demo";
import { client } from "../lib/client";
import demoPlan from "../fixtures/plan.json";

interface PlanCandidate {
  node_id: string;
  node_name: string;
  paper_id: string;
  paper_code: string;
  chapter_id?: string;
  chapter_name?: string;
  status: "not_started" | "in_progress" | "done";
  importance: number;
  priority_score?: number;
  weak?: boolean;
  freq_hits?: number;
  freq_window?: number;
  exam_marks_total?: number;
  reason?: string;
}

interface PlanResponse {
  budget_items: number;
  total_allocated: number;
  hours_per_week: number;
  minutes_per_subtopic: number;
  items: PlanCandidate[];
}

export function Plan() {
  const [hoursPerWeek, setHoursPerWeek] = useState<number>(20);
  const [selectedPaper, setSelectedPaper] = useState<string>("all");
  const [selectedGroup, setSelectedGroup] = useState<string>("all");
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);

  const { data: apiPlan, isLoading, refetch } = useQuery({
    queryKey: ["study-plan", hoursPerWeek, selectedPaper, selectedGroup],
    queryFn: async () => {
      if (isDemoMode()) {
        return null;
      }
      try {
        const queryParams: Record<string, any> = {
          hours: hoursPerWeek,
        };
        if (selectedPaper !== "all") {
          queryParams.paper = selectedPaper;
        }
        if (selectedGroup !== "all") {
          queryParams.group = parseInt(selectedGroup, 10);
        }

        const res = await client.GET("/api/v1/plan", {
          params: {
            query: queryParams,
          },
        });
        if (res.data) {
          return res.data as unknown as PlanResponse;
        }
      } catch (err) {
        console.warn("Failed fetching live plan, falling back to demo:", err);
      }
      return null;
    },
  });

  const handleRegenerate = async () => {
    setIsRegenerating(true);
    await refetch();
    setTimeout(() => setIsRegenerating(false), 500);
  };

  // Raw items from API or demo fixtures
  const planItems: PlanCandidate[] = useMemo(() => {
    if (apiPlan?.items && apiPlan.items.length > 0) {
      return apiPlan.items;
    }
    // Fallback to demo plan
    return (demoPlan as any[]).flatMap((d) =>
      d.items.map((it: any) => ({
        node_id: it.node_id,
        node_name: it.title,
        paper_id: `s2023.${it.paper_code}`,
        paper_code: it.paper_code,
        status: it.status,
        importance: it.importance,
        reason: it.reason,
      }))
    );
  }, [apiPlan]);

  // Group items into days (approx 3 items per day)
  const daysSchedule = useMemo(() => {
    const days = [
      { name: "TODAY", label: "Monday, Current Week", isToday: true },
      { name: "TUESDAY", label: "Day 2", isToday: false },
      { name: "WEDNESDAY", label: "Day 3", isToday: false },
      { name: "THURSDAY", label: "Day 4", isToday: false },
      { name: "FRIDAY", label: "Day 5", isToday: false },
      { name: "SATURDAY", label: "Day 6 (Review & Consolidate)", isToday: false },
      { name: "SUNDAY", label: "Day 7 (Mock Practice)", isToday: false },
    ];

    const itemsPerDay = Math.max(2, Math.ceil(planItems.length / 5));
    return days.slice(0, 5).map((d, idx) => {
      const start = idx * itemsPerDay;
      const end = start + itemsPerDay;
      return {
        ...d,
        items: planItems.slice(start, end),
      };
    }).filter(d => d.items.length > 0);
  }, [planItems]);

  const numIcons = ["①", "②", "③", "④", "⑤", "⑥"];

  return (
    <div className="max-w-[1000px] mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-stone-200 dark:border-stone-800">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <Calendar className="w-5 h-5" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-stone-900 dark:text-white">
              Weekly Study Plan
            </h1>
          </div>
          <p className="text-xs text-stone-500 mt-1">
            Greedy budget allocation optimizing for historical exam probability, section weightage, and weak areas.
          </p>
        </div>

        {/* Filter Controls */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Hours per week */}
          <div className="relative">
            <select
              value={hoursPerWeek}
              onChange={(e) => setHoursPerWeek(Number(e.target.value))}
              className="appearance-none pl-3 pr-7 py-1.5 text-xs font-semibold rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer shadow-sm"
            >
              <option value={15}>15 hrs/week (~2 hrs/day)</option>
              <option value={20}>20 hrs/week (~3 hrs/day)</option>
              <option value={28}>28 hrs/week (~4 hrs/day)</option>
              <option value={35}>35 hrs/week (~5 hrs/day)</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-stone-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Group Filter */}
          <div className="relative">
            <select
              value={selectedGroup}
              onChange={(e) => {
                setSelectedGroup(e.target.value);
                setSelectedPaper("all");
              }}
              className="appearance-none pl-3 pr-7 py-1.5 text-xs font-semibold rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer shadow-sm"
            >
              <option value="all">All Groups</option>
              <option value="1">Group 1</option>
              <option value="2">Group 2</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-stone-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Paper Filter */}
          <div className="relative">
            <select
              value={selectedPaper}
              onChange={(e) => setSelectedPaper(e.target.value)}
              className="appearance-none pl-3 pr-7 py-1.5 text-xs font-semibold rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer shadow-sm"
            >
              <option value="all">All Papers</option>
              <option value="P1">P1 - FR</option>
              <option value="P2">P2 - AFM</option>
              <option value="P3">P3 - Audit</option>
              <option value="P4">P4 - DT</option>
              <option value="P5">P5 - IDT</option>
              <option value="P6">P6 - IBS</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-stone-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Regenerate Button */}
          <button
            type="button"
            onClick={handleRegenerate}
            disabled={isRegenerating || isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 hover:bg-indigo-100 text-indigo-700 dark:text-indigo-300 transition-colors shadow-sm disabled:opacity-50"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isRegenerating ? "animate-spin" : ""}`} />
            <span>Regenerate ↺</span>
          </button>
        </div>
      </div>

      {/* Plan Timeline Days */}
      <div className="space-y-6">
        {isLoading ? (
          <div className="p-12 text-center space-y-3 bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800">
            <div className="h-6 w-48 bg-stone-200 dark:bg-stone-800 rounded animate-pulse mx-auto" />
            <div className="h-4 w-64 bg-stone-200 dark:bg-stone-800 rounded animate-pulse mx-auto" />
          </div>
        ) : daysSchedule.length === 0 ? (
          <div className="p-12 text-center bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 space-y-2">
            <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto" />
            <h3 className="font-bold text-stone-900 dark:text-white">All caught up!</h3>
            <p className="text-xs text-stone-500">
              No pending subtopics for the selected filters. Increase hours or switch paper scope.
            </p>
          </div>
        ) : (
          daysSchedule.map((day) => (
            <div
              key={day.name}
              className={`rounded-2xl border ${
                day.isToday
                  ? "bg-white dark:bg-stone-900 border-indigo-200 dark:border-indigo-900/60 shadow-sm"
                  : "bg-white/80 dark:bg-stone-900/60 border-stone-200 dark:border-stone-800"
              } overflow-hidden`}
            >
              {/* Day Section Header */}
              <div
                className={`px-6 py-3.5 border-b flex items-center justify-between ${
                  day.isToday
                    ? "bg-indigo-50/70 dark:bg-indigo-950/40 border-indigo-100 dark:border-indigo-900/50"
                    : "bg-stone-50 dark:bg-stone-800/40 border-stone-100 dark:border-stone-800"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`font-black text-xs tracking-wider uppercase ${
                      day.isToday
                        ? "text-indigo-700 dark:text-indigo-400"
                        : "text-stone-700 dark:text-stone-300"
                    }`}
                  >
                    {day.name}
                  </span>
                  <span className="text-xs text-stone-400 font-medium">· {day.label}</span>
                </div>

                <div className="flex items-center gap-2 text-xs font-semibold text-stone-500">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{day.items.length * 45} mins total</span>
                </div>
              </div>

              {/* Items for this day */}
              <div className="divide-y divide-stone-100 dark:divide-stone-800/80">
                {day.items.map((item, idx) => {
                  const isDone = item.status === "done";
                  const isStarted = item.status === "in_progress";

                  return (
                    <div
                      key={item.node_id}
                      className={`p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 transition-colors ${
                        isDone
                          ? "bg-stone-50/50 dark:bg-stone-900/20 opacity-70"
                          : "hover:bg-stone-50/60 dark:hover:bg-stone-800/40"
                      }`}
                    >
                      <div className="space-y-1.5 flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-base font-bold text-indigo-600 dark:text-indigo-400">
                            {numIcons[idx] || `(${idx + 1})`}
                          </span>
                          <h3
                            className={`font-semibold text-sm md:text-base text-stone-900 dark:text-stone-100 truncate ${
                              isDone ? "line-through text-stone-400 dark:text-stone-500" : ""
                            }`}
                          >
                            {item.node_name}
                          </h3>
                          <ImportanceDots score={item.importance} size="sm" />
                          <span className="text-xs text-stone-400 font-medium">
                            · 45 min
                          </span>
                        </div>

                        <div className="flex items-center gap-2 text-xs text-stone-500 flex-wrap">
                          <span className="px-1.5 py-0.5 rounded font-bold bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300">
                            {item.paper_code}
                          </span>
                          <span>·</span>
                          <span className="capitalize">
                            {isDone ? (
                              <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                                ✓ Done
                              </span>
                            ) : isStarted ? (
                              <span className="text-amber-600 dark:text-amber-400 font-medium">
                                In progress
                              </span>
                            ) : (
                              "Not started"
                            )}
                          </span>
                          {item.reason && (
                            <>
                              <span>·</span>
                              <span className="text-stone-600 dark:text-stone-400 italic">
                                {item.reason}
                              </span>
                            </>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-3 shrink-0 self-end md:self-center">
                        <Link
                          to={`/papers/${item.paper_code}/${item.node_id}`}
                          className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                            isDone
                              ? "bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400 hover:bg-stone-200"
                              : isStarted
                              ? "bg-amber-500 hover:bg-amber-600 text-white shadow-sm"
                              : "bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm"
                          }`}
                        >
                          <span>{isDone ? "Review" : isStarted ? "Continue" : "Start"}</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
