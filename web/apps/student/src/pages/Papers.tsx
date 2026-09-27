import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  RotateCcw,
  Flag,
  ChevronDown,
} from "lucide-react";
import { ImportanceDots } from "../components/ImportanceDots";
import { ProgressRing } from "../components/ProgressRing";
import { isDemoMode } from "../lib/demo";
import { client } from "../lib/client";
import demoPapers from "../fixtures/papers.json";

export interface PaperSummaryItem {
  id: string;
  code: string;
  name: string;
  group_no: number | null;
  total_subtopics: number;
  completed_subtopics: number;
  raw_progress_pct: number;
  weighted_coverage_pct: number;
  avg_importance?: number;
  revision_due_count?: number;
  weak_flag_count?: number;
}

export function Papers() {
  const [selectedGroup, setSelectedGroup] = useState<"all" | "1" | "2">("all");
  const [sortBy, setSortBy] = useState<"group" | "coverage_asc" | "importance_desc">("group");

  const { data: livePapers } = useQuery({
    queryKey: ["papers"],
    queryFn: async () => {
      if (isDemoMode()) {
        return null;
      }
      try {
        const res = await client.GET("/api/v1/papers");
        if (res.data) {
          return res.data as PaperSummaryItem[];
        }
      } catch (err) {
        console.warn("Falling back to demo papers:", err);
      }
      return null;
    },
  });

  // Blend live API with demo stats (for avg_importance & due_revision if not in basic API response)
  const papers: PaperSummaryItem[] = (livePapers ?? demoPapers.map((dp, i) => ({
    id: `s2023.${dp.code}`,
    code: dp.code,
    name: dp.name,
    group_no: i < 3 ? 1 : 2,
    total_subtopics: dp.total_subtopics,
    completed_subtopics: dp.completed_subtopics,
    raw_progress_pct: dp.coverage_pct,
    weighted_coverage_pct: dp.coverage_pct,
    avg_importance: dp.avg_importance,
    revision_due_count: dp.due_revision,
    weak_flag_count: i === 0 ? 3 : i === 1 ? 1 : 0,
  }))).map((p) => {
    // Fill in defaults if live API didn't include optional enrichment
    return {
      ...p,
      avg_importance: p.avg_importance ?? 0.72,
      revision_due_count: p.revision_due_count ?? (p.code === "P1" ? 3 : p.code === "P2" ? 1 : 0),
      weak_flag_count: p.weak_flag_count ?? (p.code === "P1" ? 2 : 0),
    };
  });

  // Filter
  const filtered = papers.filter((p) => {
    if (selectedGroup === "1") return p.group_no === 1;
    if (selectedGroup === "2") return p.group_no === 2;
    return true;
  });

  // Sort
  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === "coverage_asc") {
      return (a.weighted_coverage_pct || a.raw_progress_pct) - (b.weighted_coverage_pct || b.raw_progress_pct);
    }
    if (sortBy === "importance_desc") {
      return (b.avg_importance ?? 0) - (a.avg_importance ?? 0);
    }
    // Default: Group sort then code
    const gA = a.group_no ?? 1;
    const gB = b.group_no ?? 1;
    if (gA !== gB) return gA - gB;
    return a.code.localeCompare(b.code);
  });

  return (
    <div className="max-w-[1200px] mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Page Header with Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-stone-200 dark:border-stone-800">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-stone-900 dark:text-white">
            Papers Overview
          </h1>
          <p className="text-xs text-stone-500 mt-1">
            Navigate the 6 CA Final papers, review syllabus depth, and inspect exam weightage
          </p>
        </div>

        {/* Filter and Sort controls */}
        <div className="flex items-center gap-3">
          {/* Group Filter */}
          <div className="relative">
            <select
              value={selectedGroup}
              onChange={(e) => setSelectedGroup(e.target.value as "all" | "1" | "2")}
              className="appearance-none pl-3 pr-8 py-1.5 text-xs font-semibold rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 hover:border-stone-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer shadow-sm"
            >
              <option value="all">Group: All Papers</option>
              <option value="1">Group 1 (P1–P3)</option>
              <option value="2">Group 2 (P4–P6)</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-stone-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Sort Dropdown */}
          <div className="relative">
            <select
              value={sortBy}
              onChange={(e) =>
                setSortBy(e.target.value as "group" | "coverage_asc" | "importance_desc")
              }
              className="appearance-none pl-3 pr-8 py-1.5 text-xs font-semibold rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 hover:border-stone-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer shadow-sm"
            >
              <option value="group">Sort: By Group</option>
              <option value="coverage_asc">Sort: Lowest Coverage First</option>
              <option value="importance_desc">Sort: Highest Importance</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-stone-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* 3-Column Grid of Paper Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sorted.map((paper) => {
          const coveragePct = paper.weighted_coverage_pct || paper.raw_progress_pct || 0;
          const avgImp = paper.avg_importance ?? 0.72;
          const weakCount = paper.weak_flag_count ?? 0;
          const revCount = paper.revision_due_count ?? 0;

          return (
            <Link
              key={paper.id || paper.code}
              to={`/papers/${paper.code}`}
              className="group flex flex-col justify-between p-6 rounded-2xl bg-white dark:bg-stone-900 border border-stone-200/90 dark:border-stone-800 shadow-sm hover:shadow-md hover:border-indigo-300 dark:hover:border-indigo-900/60 transition-all text-left"
            >
              {/* Card Header: Code, Group, Title */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-1 rounded-lg font-black text-xs bg-indigo-50 dark:bg-indigo-950/70 text-indigo-600 dark:text-indigo-400">
                      {paper.code}
                    </span>
                    <span className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider">
                      Group {paper.group_no ?? 1}
                    </span>
                  </div>

                  {/* Badges for weak or revision alerts */}
                  <div className="flex items-center gap-1.5">
                    {weakCount > 0 && (
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-orange-50 dark:bg-orange-950/60 text-orange-600 dark:text-orange-400 border border-orange-200/50 dark:border-orange-900/40"
                        title={`${weakCount} weak flag subtopics needing urgent study`}
                      >
                        <Flag className="w-3 h-3 fill-orange-500" />
                        <span>{weakCount}</span>
                      </span>
                    )}
                    {revCount > 0 && (
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border border-amber-200/50 dark:border-amber-900/40"
                        title={`${revCount} revisions due today`}
                      >
                        <RotateCcw className="w-3 h-3" />
                        <span>{revCount}</span>
                      </span>
                    )}
                  </div>
                </div>

                <h2 className="text-base font-bold text-stone-900 dark:text-stone-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors line-clamp-2">
                  {paper.name}
                </h2>
              </div>

              {/* Card Center: Progress Ring & Average Importance */}
              <div className="my-6 flex items-center justify-between p-4 rounded-xl bg-stone-50 dark:bg-stone-800/40 border border-stone-100 dark:border-stone-800">
                <div className="flex items-center gap-3">
                  <ProgressRing
                    percentage={coveragePct}
                    size={64}
                    strokeWidth={6}
                    showText={true}
                  />
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-stone-400">
                      Syllabus Done
                    </div>
                    <div className="text-xs font-semibold text-stone-800 dark:text-stone-200">
                      {paper.completed_subtopics} / {paper.total_subtopics}
                    </div>
                    <div className="text-[10px] text-stone-400">subtopics completed</div>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-stone-400 mb-1">
                    Avg Importance
                  </div>
                  <ImportanceDots score={avgImp} size="md" />
                </div>
              </div>

              {/* Card Footer: Metadata and CTA */}
              <div className="pt-3 border-t border-stone-100 dark:border-stone-800 flex items-center justify-between text-xs">
                <span className="text-stone-500 font-medium">
                  {paper.total_subtopics} canonical subtopics
                </span>
                <span className="font-semibold text-indigo-600 dark:text-indigo-400 flex items-center gap-1 group-hover:translate-x-0.5 transition-transform">
                  <span>Open Paper</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
