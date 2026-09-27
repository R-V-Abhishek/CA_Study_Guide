import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Flame,
  ArrowRight,
  RotateCcw,
  CheckCircle2,
  Sparkles,
} from "lucide-react";
import { ImportanceDots } from "../components/ImportanceDots";
import { ProgressRing } from "../components/ProgressRing";
import { isDemoMode } from "../lib/demo";
import { client } from "../lib/client";
import demoDashboard from "../fixtures/dashboard.json";

interface DashboardData {
  target_attempt: string;
  days_remaining?: number;
  streak_days?: number;
  total_subtopics: number;
  done_subtopics: number;
  in_progress_subtopics: number;
  overall_progress_pct: number;
  group1_progress_pct: number;
  group2_progress_pct: number;
  weighted_coverage?: {
    overall_coverage_pct?: number;
    papers?: Array<{
      paper_id: string;
      code: string;
      name: string;
      raw_coverage_pct: number;
      weighted_coverage_pct: number;
    }>;
  };
  plan_preview?: Array<{
    node_id: string;
    paper_id?: string;
    paper_code?: string;
    title?: string;
    subtopic_name?: string;
    importance?: number;
    estimated_minutes?: number;
    status?: string;
    reasons?: string[];
  }>;
  revision_due_count?: number;
  weak_subtopics?: Array<{
    node_id: string;
    name: string;
    paper_code: string;
    paper_id?: string;
    importance: number;
    freq_hits: number;
    freq_window: number;
  }>;
}

export function Dashboard() {
  const { data: apiData } = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => {
      if (isDemoMode()) {
        return null;
      }
      try {
        const res = await client.GET("/api/v1/dashboard");
        if (res.data) {
          return res.data as unknown as DashboardData;
        }
      } catch (err) {
        console.warn("Failed fetching live dashboard, falling back to demo:", err);
      }
      return null;
    },
  });

  // Blend live API data with fallback demo data if running in demo or initial state
  const data: DashboardData = apiData ?? {
    target_attempt: demoDashboard.target_attempt,
    days_remaining: demoDashboard.days_remaining,
    streak_days: demoDashboard.streak_days,
    total_subtopics: demoDashboard.total_subtopics,
    done_subtopics: demoDashboard.completed_subtopics,
    in_progress_subtopics: 12,
    overall_progress_pct: demoDashboard.overall_coverage_pct,
    group1_progress_pct: 61,
    group2_progress_pct: 54,
    revision_due_count: demoDashboard.due_revision_count,
    plan_preview: demoDashboard.study_today.map((s) => ({
      node_id: s.node_id,
      paper_id: s.paper_code,
      paper_code: s.paper_code,
      title: s.title,
      importance: s.importance,
      estimated_minutes: s.estimated_minutes,
      status: s.status,
      reasons: ["High exam frequency (6 of last 8 attempts)", "12-16 marks typical"],
    })),
    weak_subtopics: [
      {
        node_id: "s2023.P1.CH01.T01.S01",
        name: "Ind AS 115 — Revenue from Contracts with Customers",
        paper_code: "P1",
        paper_id: "s2023.P1",
        importance: 0.92,
        freq_hits: 6,
        freq_window: 8,
      },
    ],
  };

  // Get current hour for greeting
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  // Days to target attempt estimate (May 2026 / Nov 2026)
  const daysToExam = data.days_remaining ?? 54;
  const streakDays = data.streak_days ?? 14;

  const todayFocusItems = data.plan_preview && data.plan_preview.length > 0
    ? data.plan_preview.slice(0, 4)
    : [
        {
          node_id: "s2023.P1.CH01.T01.S01",
          paper_code: "P1",
          title: "Ind AS 115 — Revenue Recognition & Bundle Contracts",
          importance: 0.92,
          estimated_minutes: 45,
          status: "in_progress",
          reasons: ["Asked 6× in last 8 exams", "12–16 marks typical"],
        },
        {
          node_id: "s2023.P3.CH03.T01.S01",
          paper_code: "P3",
          title: "SA 700 — Forming an Opinion and Reporting on Financials",
          importance: 0.85,
          estimated_minutes: 30,
          status: "not_started",
          reasons: ["Asked 5× in recent papers", "8–12 marks typical"],
        },
        {
          node_id: "s2023.P4.CH04.T02.S01",
          paper_code: "P4",
          title: "Sec 44AB — Mandatory Tax Audit Thresholds",
          importance: 0.78,
          estimated_minutes: 30,
          status: "not_started",
          reasons: ["Weak coverage flag", "Frequent 8-mark problem"],
        },
      ];

  const paperList = [
    { code: "P1", name: "Financial Reporting", pct: 67 },
    { code: "P2", name: "Adv Financial Mgmt", pct: 72 },
    { code: "P3", name: "Adv Auditing & Ethics", pct: 48 },
    { code: "P4", name: "Direct Tax Laws", pct: 51 },
    { code: "P5", name: "Indirect Tax Laws", pct: 38 },
    { code: "P6", name: "Integrated Business", pct: 90 },
  ];

  return (
    <div className="max-w-[1200px] mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Top Banner / Hero */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-stone-200 dark:border-stone-800">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-orange-100 dark:bg-orange-950/50 text-orange-700 dark:text-orange-400 text-xs font-bold tracking-wide">
              <Flame className="w-4 h-4 fill-orange-500 text-orange-500" />
              <span>{streakDays} DAY STREAK</span>
            </span>
            <span className="text-xs text-stone-400 font-medium">·</span>
            <span className="text-xs font-semibold text-stone-600 dark:text-stone-400 uppercase tracking-wider">
              Target: {data.target_attempt}
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-stone-900 dark:text-white mt-2">
            {greeting}. <span className="text-indigo-600 dark:text-indigo-400">{daysToExam} days</span> to exams.
          </h1>
        </div>

        <div className="flex items-center gap-4 bg-white dark:bg-stone-900 p-3.5 rounded-2xl border border-stone-200/80 dark:border-stone-800 shadow-sm">
          <ProgressRing
            percentage={data.overall_progress_pct}
            size={68}
            strokeWidth={6}
            subtext="overall"
          />
          <div className="pr-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-stone-400">
              Syllabus Progress
            </div>
            <div className="text-lg font-bold text-stone-900 dark:text-stone-100">
              {data.done_subtopics} <span className="text-xs text-stone-400 font-normal">/ {data.total_subtopics} subtopics</span>
            </div>
            <div className="text-xs text-stone-500 mt-0.5">
              {data.in_progress_subtopics} in progress
            </div>
          </div>
        </div>
      </div>

      {/* TODAY'S FOCUS (Single most important hero section above the fold) */}
      <section className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-stone-100 dark:border-stone-800/80 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-stone-900 dark:text-white">
                TODAY'S FOCUS
              </h2>
              <p className="text-xs text-stone-500">
                Highest exam-yield subtopics selected by historical probability & weak coverage
              </p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300">
            {todayFocusItems.length} prioritized
          </span>
        </div>

        <div className="divide-y divide-stone-100 dark:divide-stone-800">
          {todayFocusItems.map((item, idx) => {
            const paperCode = item.paper_code || "P1";
            const isStarted = item.status === "in_progress";
            const numIcons = ["①", "②", "③", "④", "⑤"];

            return (
              <div
                key={item.node_id || idx}
                className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-stone-50/75 dark:hover:bg-stone-800/50 transition-colors"
              >
                <div className="space-y-1.5 flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-base font-bold text-indigo-600 dark:text-indigo-400">
                      {numIcons[idx] || `(${idx + 1})`}
                    </span>
                    <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm md:text-base truncate">
                      {item.title || item.subtopic_name}
                    </h3>
                    <ImportanceDots score={item.importance ?? 0.8} size="sm" />
                    <span className="text-xs font-medium text-stone-400">
                      · {item.estimated_minutes ?? 45} min
                    </span>
                  </div>

                  <div className="flex items-center gap-2 text-xs text-stone-500 flex-wrap">
                    <span className="px-1.5 py-0.5 rounded font-bold bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300">
                      {paperCode}
                    </span>
                    <span>·</span>
                    <span className="capitalize">
                      {isStarted ? (
                        <span className="text-amber-600 dark:text-amber-400 font-medium">In progress</span>
                      ) : (
                        "Not started"
                      )}
                    </span>
                    {item.reasons && item.reasons.length > 0 && (
                      <>
                        <span>·</span>
                        <span className="text-stone-600 dark:text-stone-400">
                          {item.reasons.join(" · ")}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3 self-end md:self-center shrink-0">
                  <Link
                    to={`/papers/${paperCode}/${item.node_id}`}
                    className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                      isStarted
                        ? "bg-amber-500 hover:bg-amber-600 text-white shadow-sm"
                        : "bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm"
                    }`}
                  >
                    <span>{isStarted ? "Continue" : "Study Now"}</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>

        <div className="p-4 bg-stone-50/80 dark:bg-stone-800/40 border-t border-stone-100 dark:border-stone-800 flex items-center justify-between text-xs">
          <Link
            to="/plan"
            className="font-semibold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1"
          >
            <span>Full weekly study plan</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
          <span className="text-stone-500">
            Revision due today: <strong className="text-stone-800 dark:text-stone-200">{data.revision_due_count ?? 3} subtopics</strong>
          </span>
        </div>
      </section>

      {/* Two-Column Grid: COVERAGE and REVISION DUE */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: COVERAGE */}
        <section className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 p-6 shadow-sm space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              <h2 className="text-sm font-bold uppercase tracking-wider text-stone-700 dark:text-stone-300">
                COVERAGE
              </h2>
            </div>
            <Link
              to="/progress"
              className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
            >
              Full breakdown →
            </Link>
          </div>

          {/* Group summaries */}
          <div className="grid grid-cols-3 gap-3 p-3.5 rounded-xl bg-stone-50 dark:bg-stone-800/60 text-center">
            <div>
              <div className="text-[11px] font-semibold text-stone-400 uppercase">Overall</div>
              <div className="text-xl font-bold text-stone-900 dark:text-stone-100 mt-0.5">
                {Math.round(data.overall_progress_pct)}%
              </div>
            </div>
            <div className="border-x border-stone-200 dark:border-stone-700">
              <div className="text-[11px] font-semibold text-stone-400 uppercase">Group 1</div>
              <div className="text-xl font-bold text-stone-900 dark:text-stone-100 mt-0.5">
                {Math.round(data.group1_progress_pct)}%
              </div>
            </div>
            <div>
              <div className="text-[11px] font-semibold text-stone-400 uppercase">Group 2</div>
              <div className="text-xl font-bold text-stone-900 dark:text-stone-100 mt-0.5">
                {Math.round(data.group2_progress_pct)}%
              </div>
            </div>
          </div>

          {/* Paper-by-Paper Progress Bars */}
          <div className="space-y-3 pt-2">
            {paperList.map((paper) => (
              <Link
                key={paper.code}
                to={`/papers/${paper.code}`}
                className="group flex items-center justify-between gap-4 p-2 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800/60 transition-colors"
              >
                <div className="w-12 font-bold text-xs text-indigo-600 dark:text-indigo-400">
                  {paper.code}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-medium text-stone-700 dark:text-stone-300 truncate">
                      {paper.name}
                    </span>
                    <span className="font-semibold text-stone-500">{paper.pct}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-stone-100 dark:bg-stone-800 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ease-out ${
                        paper.pct >= 66
                          ? "bg-emerald-500"
                          : paper.pct >= 33
                          ? "bg-amber-500"
                          : "bg-rose-500"
                      }`}
                      style={{ width: `${paper.pct}%` }}
                    />
                  </div>
                </div>
                <ArrowRight className="w-4 h-4 text-stone-300 group-hover:text-stone-600 dark:group-hover:text-stone-300 transition-colors shrink-0" />
              </Link>
            ))}
          </div>
        </section>

        {/* Right Column: REVISION DUE */}
        <section className="bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 p-6 shadow-sm flex flex-col justify-between space-y-5">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <RotateCcw className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                <h2 className="text-sm font-bold uppercase tracking-wider text-stone-700 dark:text-stone-300">
                  REVISION DUE
                </h2>
              </div>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-orange-100 dark:bg-orange-950/70 text-orange-700 dark:text-orange-400">
                {data.revision_due_count ?? 3} due today
              </span>
            </div>

            <p className="text-xs text-stone-500">
              Spaced repetition intervals (3, 7, 21, 60 days) to prevent memory decay.
            </p>

            <div className="space-y-3">
              <div className="p-3.5 rounded-xl bg-stone-50 dark:bg-stone-800/60 border border-stone-200 dark:border-stone-700/60 space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-indigo-600 dark:text-indigo-400">P1</span>
                  <span className="text-stone-400 font-medium">Last: 21 days ago</span>
                </div>
                <div className="font-semibold text-sm text-stone-900 dark:text-stone-100">
                  Ind AS 116 — Lease Accounting & Remeasurement
                </div>
                <div className="text-xs text-amber-600 dark:text-amber-400 font-medium pt-0.5">
                  Repetition #3 due
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-stone-50 dark:bg-stone-800/60 border border-stone-200 dark:border-stone-700/60 space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-indigo-600 dark:text-indigo-400">P2</span>
                  <span className="text-stone-400 font-medium">Last: 7 days ago</span>
                </div>
                <div className="font-semibold text-sm text-stone-900 dark:text-stone-100">
                  Foreign Exchange Risk — Forward Rate Agreements
                </div>
                <div className="text-xs text-amber-600 dark:text-amber-400 font-medium pt-0.5">
                  Repetition #2 due
                </div>
              </div>
            </div>
          </div>

          <div className="pt-2">
            <Link
              to="/revision"
              className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs transition-colors shadow-sm"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Open Spaced Revision Queue ({data.revision_due_count ?? 3} items) →</span>
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
