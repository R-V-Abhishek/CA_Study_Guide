import { useState, useMemo, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Search,
  CheckCircle2,
  Clock,
  Circle,
  Flag,
  Sparkles,
} from "lucide-react";
import { ImportanceDots } from "../components/ImportanceDots";
import { ProgressRing } from "../components/ProgressRing";
import { SubtopicDetail } from "../components/SubtopicDetail";
import { client } from "../lib/client";

interface SubtopicNode {
  id: string;
  name: string;
  seq: number;
  status: "not_started" | "in_progress" | "done";
  notes?: string | null;
  first_done_at?: string | null;
  last_revised_at?: string | null;
  importance: number;
  freq_hits: number;
  freq_window: number;
  weak: boolean;
  applicable: boolean;
}

interface TopicNode {
  id: string;
  name: string;
  seq: number;
  subtopics: SubtopicNode[];
}

interface ChapterNode {
  id: string;
  name: string;
  seq: number;
  weightage_min_pct?: number | null;
  weightage_max_pct?: number | null;
  weightage_section_name?: string | null;
  total_subtopics: number;
  completed_subtopics: number;
  progress_pct: number;
  topics: TopicNode[];
}

interface PaperTreeData {
  paper_id: string;
  code: string;
  name: string;
  chapters: ChapterNode[];
}

export function PaperDetail() {
  const { paperId = "P1", nodeId } = useParams<{ paperId: string; nodeId?: string }>();
  const navigate = useNavigate();

  // Search, filter, and sort state
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "all" | "not_started" | "in_progress" | "done" | "weak"
  >("all");
  const [sortBy, setSortBy] = useState<"importance" | "seq" | "not_done">("importance");
  const [expandedChapters, setExpandedChapters] = useState<Record<string, boolean>>({});

  // Query paper tree
  const { data: treeData, isLoading } = useQuery({
    queryKey: ["paper-tree", paperId],
    queryFn: async () => {
      // First try /api/v1/papers/{paper_id}/tree
      const targetParam = paperId.startsWith("s2023.") ? paperId : `s2023.${paperId.toUpperCase()}`;
      try {
        const res = await client.GET("/api/v1/papers/{paper_id}/tree", {
          params: { path: { paper_id: targetParam } },
        });
        if (res.data) {
          return res.data as unknown as PaperTreeData;
        }
      } catch (err) {
        console.warn("Failed fetching paper tree by id, trying tree?paper query:", err);
      }

      // Fallback query
      try {
        const res = await client.GET("/api/v1/tree", {
          params: { query: { paper: paperId } },
        });
        if (res.data) {
          return res.data as unknown as PaperTreeData;
        }
      } catch (err) {
        console.warn("Falling back:", err);
      }
      return null;
    },
  });

  // Calculate paper totals and statistics
  const paperStats = useMemo(() => {
    if (!treeData) return { total: 0, done: 0, inProgress: 0, pct: 0, weak: 0, allSubtopics: [] };
    let total = 0;
    let done = 0;
    let inProgress = 0;
    let weak = 0;
    const allSubs: SubtopicNode[] = [];

    treeData.chapters.forEach((ch) => {
      ch.topics.forEach((top) => {
        top.subtopics.forEach((s) => {
          total++;
          allSubs.push(s);
          if (s.status === "done") done++;
          if (s.status === "in_progress") inProgress++;
          if (s.weak) weak++;
        });
      });
    });

    const pct = total > 0 ? (done / total) * 100 : 0;
    return { total, done, inProgress, pct, weak, allSubtopics: allSubs };
  }, [treeData]);

  // Expand all chapters initially once data arrives
  useEffect(() => {
    if (treeData && Object.keys(expandedChapters).length === 0) {
      const initial: Record<string, boolean> = {};
      treeData.chapters.forEach((ch) => {
        initial[ch.id] = true;
      });
      setExpandedChapters(initial);
    }
  }, [treeData]);

  const toggleChapter = (chId: string) => {
    setExpandedChapters((prev) => ({
      ...prev,
      [chId]: !prev[chId],
    }));
  };

  // Filter and sort subtopics
  const filteredChapters = useMemo(() => {
    if (!treeData) return [];

    return treeData.chapters
      .map((chapter) => {
        const matchingTopics = chapter.topics
          .map((topic) => {
            let subs = topic.subtopics.filter((s) => {
              // Search query filter
              if (
                searchQuery &&
                !s.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
                !topic.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
                !chapter.name.toLowerCase().includes(searchQuery.toLowerCase())
              ) {
                return false;
              }

              // Status filter
              if (statusFilter === "not_started" && s.status !== "not_started") return false;
              if (statusFilter === "in_progress" && s.status !== "in_progress") return false;
              if (statusFilter === "done" && s.status !== "done") return false;
              if (statusFilter === "weak" && !s.weak) return false;

              return true;
            });

            // Sorting
            subs = [...subs].sort((a, b) => {
              if (sortBy === "importance") {
                return b.importance - a.importance;
              }
              if (sortBy === "not_done") {
                const rank = (status: string) =>
                  status === "in_progress" ? 0 : status === "not_started" ? 1 : 2;
                return rank(a.status) - rank(b.status);
              }
              return a.seq - b.seq;
            });

            return {
              ...topic,
              subtopics: subs,
            };
          })
          .filter((t) => t.subtopics.length > 0);

        return {
          ...chapter,
          topics: matchingTopics,
        };
      })
      .filter((ch) => ch.topics.length > 0);
  }, [treeData, searchQuery, statusFilter, sortBy]);

  // Top 5 importance leaders for empty-selection view
  const topImportanceLeaders = useMemo(() => {
    return [...paperStats.allSubtopics]
      .sort((a, b) => b.importance - a.importance)
      .slice(0, 5);
  }, [paperStats.allSubtopics]);

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] -my-6 -mx-4">
      {/* Top Banner Bar */}
      <header className="px-6 py-3 bg-white dark:bg-stone-900 border-b border-stone-200 dark:border-stone-800 flex items-center justify-between z-10 shrink-0">
        <div className="flex items-center gap-4">
          <Link
            to="/papers"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Papers</span>
          </Link>

          <div className="h-4 w-px bg-stone-200 dark:bg-stone-800" />

          <div className="flex items-center gap-2">
            <span className="font-black text-sm px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/70 text-indigo-600 dark:text-indigo-400">
              {treeData?.code || paperId}
            </span>
            <h1 className="font-bold text-sm md:text-base text-stone-900 dark:text-stone-100">
              {treeData?.name || "Paper Syllabus"}
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {paperStats.weak > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-orange-50 dark:bg-orange-950/50 text-orange-700 dark:text-orange-400 border border-orange-200/60 dark:border-orange-900/40">
              <Flag className="w-3.5 h-3.5 fill-orange-500" />
              <span>{paperStats.weak} weak flags</span>
            </span>
          )}

          <div className="flex items-center gap-2 bg-stone-50 dark:bg-stone-800/60 px-3 py-1 rounded-xl border border-stone-200/60 dark:border-stone-700/60">
            <ProgressRing
              percentage={paperStats.pct}
              size={36}
              strokeWidth={4}
              showText={false}
            />
            <div className="text-right">
              <div className="text-[10px] uppercase font-bold text-stone-400">Coverage</div>
              <div className="text-xs font-bold text-stone-800 dark:text-stone-200">
                {Math.round(paperStats.pct)}%
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Two-Pane Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Pane: Syllabus Tree (Width: 380px desktop, full width mobile if no node selected) */}
        <aside
          className={`w-full lg:w-[400px] shrink-0 border-r border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900/40 flex flex-col ${
            nodeId ? "hidden lg:flex" : "flex"
          }`}
        >
          {/* Controls: Search, Filter, Sort */}
          <div className="p-4 border-b border-stone-200 dark:border-stone-800 space-y-3 bg-stone-50/50 dark:bg-stone-900/70">
            {/* Search Input */}
            <div className="relative">
              <Search className="w-4 h-4 text-stone-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter topics & subtopics…"
                className="w-full pl-9 pr-3 py-1.5 rounded-xl text-xs bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-700 text-stone-900 dark:text-white placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm"
              />
            </div>

            {/* Sort & Status Filter Bar */}
            <div className="flex items-center justify-between gap-2">
              <div className="relative flex-1">
                <select
                  value={sortBy}
                  onChange={(e) =>
                    setSortBy(e.target.value as "importance" | "seq" | "not_done")
                  }
                  className="w-full appearance-none pl-2.5 pr-7 py-1 text-[11px] font-semibold rounded-lg bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-700 text-stone-700 dark:text-stone-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                >
                  <option value="importance">Sort: Importance (High Yield)</option>
                  <option value="seq">Sort: Syllabus Order</option>
                  <option value="not_done">Sort: Not Done First</option>
                </select>
                <ChevronDown className="w-3 h-3 text-stone-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>

              {/* Status Filter Dropdown */}
              <div className="relative flex-1">
                <select
                  value={statusFilter}
                  onChange={(e) =>
                    setStatusFilter(
                      e.target.value as "all" | "not_started" | "in_progress" | "done" | "weak"
                    )
                  }
                  className="w-full appearance-none pl-2.5 pr-7 py-1 text-[11px] font-semibold rounded-lg bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-700 text-stone-700 dark:text-stone-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                >
                  <option value="all">Status: All (Show all)</option>
                  <option value="not_started">Status: Not Started</option>
                  <option value="in_progress">Status: In Progress</option>
                  <option value="done">Status: Done</option>
                  <option value="weak">Status: Weak Flags ⚑</option>
                </select>
                <ChevronDown className="w-3 h-3 text-stone-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>
          </div>

          {/* Tree Scroll Area */}
          <div className="flex-1 overflow-y-auto divide-y divide-stone-100 dark:divide-stone-800/80">
            {isLoading ? (
              <div className="p-6 space-y-3">
                <div className="h-6 w-3/4 bg-stone-200 dark:bg-stone-800 rounded animate-pulse" />
                <div className="h-4 w-1/2 bg-stone-200 dark:bg-stone-800 rounded animate-pulse" />
                <div className="h-4 w-2/3 bg-stone-200 dark:bg-stone-800 rounded animate-pulse" />
              </div>
            ) : filteredChapters.length === 0 ? (
              <div className="p-8 text-center text-xs text-stone-400">
                No subtopics match current search or filters.
              </div>
            ) : (
              filteredChapters.map((chapter) => {
                const isExpanded = expandedChapters[chapter.id] ?? true;

                return (
                  <div key={chapter.id} className="text-xs">
                    {/* Chapter Header Row (Click to toggle topics) */}
                    <button
                      type="button"
                      onClick={() => toggleChapter(chapter.id)}
                      className="w-full px-4 py-2.5 flex items-center justify-between text-left font-bold text-stone-800 dark:text-stone-200 bg-stone-100/60 dark:bg-stone-800/40 hover:bg-stone-100 dark:hover:bg-stone-800/70 transition-colors"
                    >
                      <div className="flex items-center gap-2 truncate pr-2">
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                        )}
                        <span className="truncate">{chapter.name}</span>
                      </div>
                      <span className="text-[10px] text-stone-400 font-semibold shrink-0">
                        {chapter.completed_subtopics}/{chapter.total_subtopics}
                      </span>
                    </button>

                    {/* Topics and Subtopics */}
                    {isExpanded && (
                      <div className="py-1">
                        {chapter.topics.map((topic) => (
                          <div key={topic.id} className="py-0.5">
                            {/* Topic label */}
                            <div className="px-5 py-1 text-[11px] font-semibold text-stone-400 truncate">
                              {topic.name}
                            </div>

                            {/* Subtopics */}
                            <div className="space-y-0.5 pl-2">
                              {topic.subtopics.map((sub) => {
                                const isSelected = sub.id === nodeId;

                                return (
                                  <button
                                    key={sub.id}
                                    type="button"
                                    onClick={() => navigate(`/papers/${paperId}/${sub.id}`)}
                                    className={`w-full px-4 py-2 flex items-center justify-between text-left transition-colors rounded-lg group ${
                                      isSelected
                                        ? "bg-indigo-50 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300 font-semibold"
                                        : "hover:bg-stone-100/80 dark:hover:bg-stone-800/50 text-stone-700 dark:text-stone-300"
                                    }`}
                                  >
                                    <div className="flex items-center gap-2 truncate pr-2">
                                      {/* Status icon badge */}
                                      {sub.status === "done" ? (
                                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                                      ) : sub.status === "in_progress" ? (
                                        <Clock className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                                      ) : (
                                        <Circle className="w-3.5 h-3.5 text-stone-300 dark:text-stone-600 shrink-0" />
                                      )}

                                      <span
                                        className="truncate text-xs"
                                        title={sub.name}
                                      >
                                        {sub.name}
                                      </span>

                                      {sub.weak && (
                                        <Flag className="w-3 h-3 text-orange-500 fill-orange-500 shrink-0" />
                                      )}
                                    </div>

                                    <ImportanceDots score={sub.importance} size="sm" />
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* Right Pane: Subtopic Inspector OR Empty Overview */}
        <main
          className={`flex-1 overflow-y-auto bg-[#FAFAF9] dark:bg-[#0C0A09] ${
            !nodeId ? "hidden lg:block" : "block"
          }`}
        >
          {nodeId ? (
            <SubtopicDetail paperId={paperId} nodeId={nodeId} />
          ) : (
            /* When nothing is selected, show Paper Overview summary */
            <div className="p-8 max-w-3xl space-y-8 animate-in fade-in duration-300">
              <div className="p-6 rounded-2xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-800 shadow-sm flex flex-col md:flex-row items-center gap-6">
                <ProgressRing
                  percentage={paperStats.pct}
                  size={96}
                  strokeWidth={8}
                  subtext="covered"
                />
                <div className="space-y-1.5 text-center md:text-left">
                  <h2 className="text-xl font-bold text-stone-900 dark:text-white">
                    {treeData?.name || "Paper Overview"}
                  </h2>
                  <p className="text-xs text-stone-500">
                    {paperStats.done} of {paperStats.total} subtopics completed ({Math.round(paperStats.pct)}%). Select any subtopic from the syllabus tree on the left to inspect past exam appearances, weightage drivers, and track progress.
                  </p>
                </div>
              </div>

              {/* Top 5 High-Yield Importance Leaders */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                  <h3 className="text-sm font-bold uppercase tracking-wider text-stone-800 dark:text-stone-200">
                    TOP HIGH-YIELD SUBTOPICS
                  </h3>
                </div>

                <div className="space-y-2.5">
                  {topImportanceLeaders.map((item, idx) => (
                    <div
                      key={item.id}
                      onClick={() => navigate(`/papers/${paperId}/${item.id}`)}
                      className="p-4 rounded-xl bg-white dark:bg-stone-900 border border-stone-200/90 dark:border-stone-800 flex items-center justify-between gap-4 cursor-pointer hover:border-indigo-400 dark:hover:border-indigo-800 transition-all shadow-sm"
                    >
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs text-indigo-600 dark:text-indigo-400">
                            #{idx + 1}
                          </span>
                          <h4 className="font-semibold text-xs md:text-sm text-stone-900 dark:text-stone-100 truncate">
                            {item.name}
                          </h4>
                        </div>
                        <div className="text-[11px] text-stone-500">
                          Appeared in {item.freq_hits} past exams · Status:{" "}
                          <span className="capitalize">{item.status.replace("_", " ")}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        <ImportanceDots score={item.importance} size="md" />
                        <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                          Study →
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
