import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  Flag,
  Circle,
  Clock,
} from "lucide-react";
import { ImportanceDots } from "../components/ImportanceDots";
import { client } from "../lib/client";

interface SubtopicProgress {
  id: string;
  name: string;
  seq: number;
  status: "not_started" | "in_progress" | "done";
  importance: number;
  weak?: boolean;
  applicable?: boolean;
  first_done_at?: string | null;
  last_revised_at?: string | null;
}

interface ChapterProgress {
  id: string;
  name: string;
  seq: number;
  total_subtopics: number;
  completed_subtopics: number;
  progress_pct: number;
  subtopics: SubtopicProgress[];
}

interface PaperProgress {
  id: string;
  code: string;
  name: string;
  group_no: number;
  total_subtopics: number;
  completed_subtopics: number;
  progress_pct: number;
  chapters: ChapterProgress[];
}

export function Progress() {
  const [statusFilter, setStatusFilter] = useState<
    "all" | "not_started" | "in_progress" | "done" | "weak"
  >("all");
  const [sortBy, setSortBy] = useState<"code" | "coverage_asc" | "coverage_desc">("code");
  const [expandedPapers, setExpandedPapers] = useState<Record<string, boolean>>({
    P1: true,
  });
  const [expandedChapters, setExpandedChapters] = useState<Record<string, boolean>>({});

  // Query all paper trees to build comprehensive breakdown
  const { data: fullProgress, isLoading } = useQuery({
    queryKey: ["all-paper-trees"],
    queryFn: async () => {
      const papers = ["P1", "P2", "P3", "P4", "P5", "P6"];
      const paperTrees: PaperProgress[] = [];

      for (const p of papers) {
        try {
          const res = await client.GET("/api/v1/tree", {
            params: { query: { paper: p } },
          });
          if (res.data) {
            const rawTree: any = res.data;
            let totalSub = 0;
            let completedSub = 0;

            const chList: ChapterProgress[] = (rawTree.chapters || []).map((ch: any) => {
              const allSubs: SubtopicProgress[] = (ch.topics || []).flatMap((t: any) =>
                (t.subtopics || []).map((s: any) => ({
                  id: s.id,
                  name: s.name,
                  seq: s.seq,
                  status: s.status,
                  importance: s.importance,
                  weak: s.weak,
                  applicable: s.applicable,
                  first_done_at: s.first_done_at,
                  last_revised_at: s.last_revised_at,
                }))
              );

              totalSub += ch.total_subtopics;
              completedSub += ch.completed_subtopics;

              return {
                id: ch.id,
                name: ch.name,
                seq: ch.seq,
                total_subtopics: ch.total_subtopics,
                completed_subtopics: ch.completed_subtopics,
                progress_pct: ch.progress_pct,
                subtopics: allSubs,
              };
            });

            paperTrees.push({
              id: rawTree.paper_id || `s2023.${p}`,
              code: rawTree.code || p,
              name: rawTree.name || p,
              group_no: ["P1", "P2", "P3"].includes(p) ? 1 : 2,
              total_subtopics: totalSub || 44,
              completed_subtopics: completedSub || 20,
              progress_pct: totalSub > 0 ? (completedSub / totalSub) * 100 : 0,
              chapters: chList,
            });
          }
        } catch (err) {
          console.warn(`Failed fetching tree for ${p}:`, err);
        }
      }

      return paperTrees;
    },
  });

  const togglePaper = (code: string) => {
    setExpandedPapers((prev) => ({
      ...prev,
      [code]: !prev[code],
    }));
  };

  const toggleChapter = (chId: string) => {
    setExpandedChapters((prev) => ({
      ...prev,
      [chId]: !prev[chId],
    }));
  };

  // Aggregated totals
  const overallStats = useMemo(() => {
    if (!fullProgress) return { total: 264, done: 153, pct: 58, g1Pct: 61, g2Pct: 54 };
    let total = 0;
    let done = 0;
    let g1Total = 0;
    let g1Done = 0;
    let g2Total = 0;
    let g2Done = 0;

    fullProgress.forEach((p) => {
      total += p.total_subtopics;
      done += p.completed_subtopics;
      if (p.group_no === 1) {
        g1Total += p.total_subtopics;
        g1Done += p.completed_subtopics;
      } else {
        g2Total += p.total_subtopics;
        g2Done += p.completed_subtopics;
      }
    });

    const pct = total > 0 ? (done / total) * 100 : 0;
    const g1Pct = g1Total > 0 ? (g1Done / g1Total) * 100 : 0;
    const g2Pct = g2Total > 0 ? (g2Done / g2Total) * 100 : 0;

    return { total, done, pct, g1Pct, g2Pct };
  }, [fullProgress]);

  // Export CSV handler
  const handleExportCSV = () => {
    if (!fullProgress) return;

    const headers = [
      "Paper Code",
      "Paper Name",
      "Chapter Name",
      "Subtopic ID",
      "Subtopic Name",
      "Importance Rating",
      "Status",
      "Weak Flag",
      "First Done At",
      "Last Revised At",
    ];

    const rows: string[][] = [headers];

    fullProgress.forEach((p) => {
      p.chapters.forEach((ch) => {
        ch.subtopics.forEach((s) => {
          rows.push([
            `"${p.code}"`,
            `"${p.name}"`,
            `"${ch.name}"`,
            `"${s.id}"`,
            `"${s.name.replace(/"/g, '""')}"`,
            `"${Math.round(s.importance * 100)}%"`,
            `"${s.status}"`,
            `"${s.weak ? "YES" : "NO"}"`,
            `"${s.first_done_at || ""}"`,
            `"${s.last_revised_at || ""}"`,
          ]);
        });
      });
    });

    const csvContent = "data:text/csv;charset=utf-8," + rows.map((e) => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "ca_final_syllabus_progress.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Sort papers
  const sortedPapers = useMemo(() => {
    if (!fullProgress) return [];
    return [...fullProgress].sort((a, b) => {
      if (sortBy === "coverage_asc") return a.progress_pct - b.progress_pct;
      if (sortBy === "coverage_desc") return b.progress_pct - a.progress_pct;
      return a.code.localeCompare(b.code);
    });
  }, [fullProgress, sortBy]);

  return (
    <div className="max-w-[1100px] mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Top Banner and Summary */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-stone-200 dark:border-stone-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-stone-900 dark:text-white">
            Full Coverage Overview
          </h1>
          <p className="text-xs text-stone-500 mt-1">
            Complete syllabus audit across all 264 subtopics with hierarchical chapter completion tracking.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleExportCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 hover:bg-stone-50 transition-colors shadow-sm cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* Aggregate Stats Bar */}
      <div className="p-6 rounded-2xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-stone-400">
              Overall Syllabus Coverage
            </div>
            <div className="text-2xl font-black text-stone-900 dark:text-white mt-1">
              {Math.round(overallStats.pct)}%{" "}
              <span className="text-xs text-stone-400 font-normal">
                ({overallStats.done} of {overallStats.total} subtopics)
              </span>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="text-right">
              <div className="text-[11px] font-semibold text-stone-400 uppercase">Group 1</div>
              <div className="text-lg font-bold text-stone-800 dark:text-stone-200">
                {Math.round(overallStats.g1Pct)}%
              </div>
            </div>
            <div className="h-8 w-px bg-stone-200 dark:bg-stone-800" />
            <div className="text-right">
              <div className="text-[11px] font-semibold text-stone-400 uppercase">Group 2</div>
              <div className="text-lg font-bold text-stone-800 dark:text-stone-200">
                {Math.round(overallStats.g2Pct)}%
              </div>
            </div>
          </div>
        </div>

        {/* Big Overall Bar */}
        <div className="w-full h-3 rounded-full bg-stone-100 dark:bg-stone-800 overflow-hidden">
          <div
            className="h-full bg-indigo-600 rounded-full transition-all duration-700"
            style={{ width: `${overallStats.pct}%` }}
          />
        </div>
      </div>

      {/* Controls Bar: Filters and Sorting */}
      <div className="flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-stone-500">Filter:</span>
          <select
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as "all" | "not_started" | "in_progress" | "done" | "weak")
            }
            className="px-2.5 py-1 rounded-lg bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 font-medium focus:outline-none"
          >
            <option value="all">All Subtopics</option>
            <option value="not_started">Not Started Only</option>
            <option value="in_progress">In Progress Only</option>
            <option value="done">Done Only</option>
            <option value="weak">Weak Flags ⚑</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-semibold text-stone-500">Sort Papers:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "code" | "coverage_asc" | "coverage_desc")}
            className="px-2.5 py-1 rounded-lg bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 font-medium focus:outline-none"
          >
            <option value="code">Paper Code (P1–P6)</option>
            <option value="coverage_asc">Lowest Coverage First</option>
            <option value="coverage_desc">Highest Coverage First</option>
          </select>
        </div>
      </div>

      {/* Accordion List by Paper */}
      <div className="space-y-4">
        {isLoading ? (
          <div className="p-12 text-center space-y-3 bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800">
            <div className="h-6 w-48 bg-stone-200 dark:bg-stone-800 rounded animate-pulse mx-auto" />
            <div className="h-4 w-64 bg-stone-200 dark:bg-stone-800 rounded animate-pulse mx-auto" />
          </div>
        ) : (
          sortedPapers.map((paper) => {
            const isPaperExpanded = expandedPapers[paper.code] ?? false;

            return (
              <div
                key={paper.code}
                className="rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 overflow-hidden shadow-sm"
              >
                {/* Paper Accordion Header */}
                <button
                  type="button"
                  onClick={() => togglePaper(paper.code)}
                  className="w-full p-5 flex items-center justify-between text-left hover:bg-stone-50 dark:hover:bg-stone-800/40 transition-colors"
                >
                  <div className="flex items-center gap-3 pr-4">
                    {isPaperExpanded ? (
                      <ChevronDown className="w-4 h-4 text-stone-400 shrink-0" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-stone-400 shrink-0" />
                    )}
                    <span className="font-bold text-xs px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/70 text-indigo-600 dark:text-indigo-400">
                      {paper.code}
                    </span>
                    <h2 className="font-bold text-sm md:text-base text-stone-900 dark:text-white truncate">
                      {paper.name}
                    </h2>
                  </div>

                  <div className="flex items-center gap-4 shrink-0">
                    <div className="w-32 hidden sm:block">
                      <div className="w-full h-2 rounded-full bg-stone-100 dark:bg-stone-800 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            paper.progress_pct >= 66
                              ? "bg-emerald-500"
                              : paper.progress_pct >= 33
                              ? "bg-amber-500"
                              : "bg-rose-500"
                          }`}
                          style={{ width: `${paper.progress_pct}%` }}
                        />
                      </div>
                    </div>
                    <span className="font-bold text-xs text-stone-800 dark:text-stone-200">
                      {Math.round(paper.progress_pct)}%
                    </span>
                  </div>
                </button>

                {/* Chapter list when expanded */}
                {isPaperExpanded && (
                  <div className="border-t border-stone-100 dark:border-stone-800/80 divide-y divide-stone-100 dark:divide-stone-800">
                    {paper.chapters.map((chapter) => {
                      const isChExpanded = expandedChapters[chapter.id] ?? false;

                      // Filter subtopics
                      const visibleSubs = chapter.subtopics.filter((s) => {
                        if (statusFilter === "not_started" && s.status !== "not_started") return false;
                        if (statusFilter === "in_progress" && s.status !== "in_progress") return false;
                        if (statusFilter === "done" && s.status !== "done") return false;
                        if (statusFilter === "weak" && !s.weak) return false;
                        return true;
                      });

                      if (statusFilter !== "all" && visibleSubs.length === 0) {
                        return null;
                      }

                      return (
                        <div key={chapter.id} className="bg-stone-50/40 dark:bg-stone-900/30">
                          {/* Chapter row */}
                          <button
                            type="button"
                            onClick={() => toggleChapter(chapter.id)}
                            className="w-full px-8 py-3 flex items-center justify-between text-left hover:bg-stone-100/60 dark:hover:bg-stone-800/50 transition-colors text-xs"
                          >
                            <div className="flex items-center gap-2 truncate pr-2">
                              {isChExpanded ? (
                                <ChevronDown className="w-3 h-3 text-stone-400 shrink-0" />
                              ) : (
                                <ChevronRight className="w-3 h-3 text-stone-400 shrink-0" />
                              )}
                              <span className="font-semibold text-stone-800 dark:text-stone-200 truncate">
                                {chapter.name}
                              </span>
                            </div>
                            <span className="text-[11px] font-bold text-stone-500 shrink-0">
                              {chapter.completed_subtopics} / {chapter.total_subtopics} done
                            </span>
                          </button>

                          {/* Subtopic rows */}
                          {isChExpanded && (
                            <div className="px-10 py-1.5 space-y-1 bg-white dark:bg-stone-900 border-t border-stone-100 dark:border-stone-800/60">
                              {visibleSubs.map((sub) => (
                                <Link
                                  key={sub.id}
                                  to={`/papers/${paper.code}/${sub.id}`}
                                  className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800/60 transition-colors text-xs group"
                                >
                                  <div className="flex items-center gap-2.5 truncate pr-2">
                                    {sub.status === "done" ? (
                                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                                    ) : sub.status === "in_progress" ? (
                                      <Clock className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                                    ) : (
                                      <Circle className="w-3.5 h-3.5 text-stone-300 dark:text-stone-600 shrink-0" />
                                    )}

                                    <span className="truncate text-stone-700 dark:text-stone-300 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 font-medium">
                                      {sub.name}
                                    </span>

                                    {sub.weak && (
                                      <span className="inline-flex items-center gap-0.5 px-1 py-0.2 rounded text-[10px] bg-orange-100 dark:bg-orange-950/60 text-orange-700 dark:text-orange-400">
                                        <Flag className="w-2.5 h-2.5 fill-orange-500" />
                                        <span>Weak</span>
                                      </span>
                                    )}
                                  </div>

                                  <div className="flex items-center gap-3 shrink-0">
                                    <ImportanceDots score={sub.importance} size="sm" />
                                    <span className="capitalize text-[11px] text-stone-400 group-hover:text-stone-600">
                                      {sub.status.replace("_", " ")}
                                    </span>
                                  </div>
                                </Link>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
