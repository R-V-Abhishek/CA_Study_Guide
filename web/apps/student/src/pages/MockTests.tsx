import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  BarChart2,
  Trash2,
  Calendar,
  X,
  FileCheck,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { isDemoMode } from "../lib/demo";
import { client } from "../lib/client";

interface MockTestItem {
  id: number;
  paper_id: string;
  paper_code: string;
  attempt_id?: string | null;
  label?: string | null;
  score: number;
  max_score: number;
  score_pct: number;
  taken_on: string;
  notes?: string | null;
}

export function MockTests() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [paperCode, setPaperCode] = useState("P1");
  const [label, setLabel] = useState("MTP Series 1 (Sep 2026)");
  const [score, setScore] = useState<number>(65);
  const [maxScore, setMaxScore] = useState<number>(100);
  const [takenOn, setTakenOn] = useState<string>(
    new Date().toISOString().split("T")[0]
  );
  const [notes, setNotes] = useState("");

  // Query mock tests
  const { data: testsData } = useQuery({
    queryKey: ["mock-tests"],
    queryFn: async () => {
      if (isDemoMode()) return null;
      try {
        const res = await client.GET("/api/v1/mock-tests");
        if (res.data) {
          return res.data as MockTestItem[];
        }
      } catch (err) {
        console.warn("Failed fetching mock tests, using demo:", err);
      }
      return null;
    },
  });

  // Blend with fallback demo scores if empty
  const mockTests: MockTestItem[] = testsData ?? [
    {
      id: 1,
      paper_id: "s2023.P1",
      paper_code: "P1",
      label: "ICAI MTP Series 1 — Sep 2026",
      score: 68,
      max_score: 100,
      score_pct: 68.0,
      taken_on: "2026-09-15",
      notes: "Strong in Ind AS 115 and 116. Need to improve consolidation balance sheet speeds.",
    },
    {
      id: 2,
      paper_id: "s2023.P2",
      paper_code: "P2",
      label: "Full Syllabus Mock Test 1",
      score: 61,
      max_score: 100,
      score_pct: 61.0,
      taken_on: "2026-08-28",
      notes: "Forex hedging calculations were accurate; lost marks in portfolio theory formula.",
    },
    {
      id: 3,
      paper_id: "s2023.P1",
      paper_code: "P1",
      label: "Chapterwise Evaluation Mock",
      score: 54,
      max_score: 100,
      score_pct: 54.0,
      taken_on: "2026-08-10",
      notes: "First attempt under strict 3-hour exam timer.",
    },
  ];

  // Create mock test mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      const res = await client.POST("/api/v1/mock-tests", {
        body: {
          paper_id: paperCode,
          label,
          score,
          max_score: maxScore,
          taken_on: takenOn,
          notes,
        },
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mock-tests"] });
      setModalOpen(false);
      setNotes("");
    },
  });

  // Delete mock test mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await client.DELETE("/api/v1/mock-tests/{test_id}", {
        params: { path: { test_id: id } },
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mock-tests"] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate();
  };

  // Prepare chart data chronologically
  const chartData = [...mockTests]
    .sort((a, b) => new Date(a.taken_on).getTime() - new Date(b.taken_on).getTime())
    .map((t) => ({
      name: `${t.paper_code} (${t.taken_on.slice(5)})`,
      score: t.score_pct,
      label: t.label || t.paper_code,
    }));

  return (
    <div className="max-w-[1000px] mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-stone-200 dark:border-stone-800">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <BarChart2 className="w-5 h-5" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-stone-900 dark:text-white">
              Mock Test Log
            </h1>
          </div>
          <p className="text-xs text-stone-500 mt-1">
            Track scores across MTPs, full syllabus tests, and time-pressured exam simulations.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white transition-colors shadow-sm cursor-pointer self-start sm:self-center"
        >
          <Plus className="w-4 h-4" />
          <span>Log Mock Score</span>
        </button>
      </div>

      {/* Score Trend Chart Card */}
      {chartData.length > 0 && (
        <div className="p-6 rounded-2xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-stone-700 dark:text-stone-300">
              SCORE PROGRESSION (%)
            </h2>
            <span className="text-xs font-semibold text-stone-500">
              Target passing: ≥ 40% per paper, ≥ 50% aggregate
            </span>
          </div>

          <div className="h-60 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                <XAxis
                  dataKey="name"
                  stroke="#888888"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  stroke="#888888"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  unit="%"
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="p-3 bg-white dark:bg-stone-800 rounded-xl border border-stone-200 dark:border-stone-700 shadow-lg text-xs space-y-1">
                          <p className="font-bold text-stone-900 dark:text-white">
                            {payload[0].payload.label}
                          </p>
                          <p className="font-semibold text-indigo-600 dark:text-indigo-400">
                            Score: {payload[0].value}%
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="#4F46E5"
                  strokeWidth={3}
                  dot={{ r: 5, fill: "#4F46E5", strokeWidth: 2, stroke: "#fff" }}
                  activeDot={{ r: 7 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* History Table */}
      <div className="rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-stone-100 dark:border-stone-800 flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-stone-700 dark:text-stone-300">
            TEST HISTORY ({mockTests.length} Records)
          </h3>
        </div>

        {mockTests.length === 0 ? (
          <div className="p-12 text-center text-xs text-stone-500">
            No mock tests logged yet. Complete a paper and record your score above.
          </div>
        ) : (
          <div className="divide-y divide-stone-100 dark:divide-stone-800">
            {mockTests.map((t) => (
              <div
                key={t.id}
                className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-stone-50/50 dark:hover:bg-stone-800/40 transition-colors"
              >
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-xs px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/70 text-indigo-600 dark:text-indigo-400">
                      {t.paper_code}
                    </span>
                    <h4 className="font-bold text-sm text-stone-900 dark:text-stone-100">
                      {t.label || "Mock Test"}
                    </h4>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-stone-400">
                    <Calendar className="w-3.5 h-3.5" />
                    <span>{t.taken_on}</span>
                    {t.notes && <span>· {t.notes}</span>}
                  </div>
                </div>

                <div className="flex items-center gap-4 shrink-0 self-end md:self-center">
                  <div className="text-right">
                    <div className="font-black text-lg text-stone-900 dark:text-stone-100">
                      {t.score} <span className="text-xs text-stone-400 font-normal">/ {t.max_score}</span>
                    </div>
                    <span
                      className={`text-xs font-bold ${
                        t.score_pct >= 60
                          ? "text-emerald-600 dark:text-emerald-400"
                          : t.score_pct >= 40
                          ? "text-amber-600 dark:text-amber-400"
                          : "text-rose-600 dark:text-rose-400"
                      }`}
                    >
                      {t.score_pct}%
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={() => deleteMutation.mutate(t.id)}
                    className="p-2 rounded-lg text-stone-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
                    title="Delete record"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal Dialog for Logging Score */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-white dark:bg-stone-900 rounded-3xl border border-stone-200 dark:border-stone-800 shadow-2xl max-w-md w-full p-6 space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-stone-800">
              <div className="flex items-center gap-2">
                <FileCheck className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                <h3 className="font-bold text-base text-stone-900 dark:text-white">
                  Log Mock Test Score
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="p-1 rounded-lg text-stone-400 hover:text-stone-700 dark:hover:text-stone-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-stone-700 dark:text-stone-300 mb-1">
                  Paper
                </label>
                <select
                  value={paperCode}
                  onChange={(e) => setPaperCode(e.target.value)}
                  className="w-full p-2.5 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-800/60 font-medium text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="P1">P1 — Financial Reporting</option>
                  <option value="P2">P2 — Advanced Financial Management</option>
                  <option value="P3">P3 — Advanced Auditing & Professional Ethics</option>
                  <option value="P4">P4 — Direct Tax Laws & International Taxation</option>
                  <option value="P5">P5 — Indirect Tax Laws</option>
                  <option value="P6">P6 — Integrated Business Solutions</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-stone-700 dark:text-stone-300 mb-1">
                  Test Label / Series
                </label>
                <input
                  type="text"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="e.g. MTP Series 1 Sep 2026, Full Mock"
                  required
                  className="w-full p-2.5 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-800/60 font-medium text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-stone-700 dark:text-stone-300 mb-1">
                    Score Achieved
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={maxScore}
                    step={0.5}
                    value={score}
                    onChange={(e) => setScore(Number(e.target.value))}
                    required
                    className="w-full p-2.5 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-800/60 font-bold text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-stone-700 dark:text-stone-300 mb-1">
                    Max Marks
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={maxScore}
                    onChange={(e) => setMaxScore(Number(e.target.value))}
                    required
                    className="w-full p-2.5 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-800/60 font-bold text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-stone-700 dark:text-stone-300 mb-1">
                  Date Taken
                </label>
                <input
                  type="date"
                  value={takenOn}
                  onChange={(e) => setTakenOn(e.target.value)}
                  required
                  className="w-full p-2.5 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-800/60 font-medium text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-stone-700 dark:text-stone-300 mb-1">
                  Key Learnings & Notes
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Which topics cost marks? Time management reflections…"
                  rows={3}
                  className="w-full p-2.5 rounded-xl border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-800/60 font-medium text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-stone-600 dark:text-stone-400 font-semibold hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold transition-colors shadow-sm disabled:opacity-50"
                >
                  {createMutation.isPending ? "Saving…" : "Save Score"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
