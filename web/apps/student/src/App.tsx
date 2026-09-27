import React from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { BookOpen, Calendar, CheckCircle2, RotateCcw, BarChart3, Moon, Sun, Flame } from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { isDemoMode } from "./lib/demo";
import demoDashboard from "./fixtures/dashboard.json";

const queryClient = new QueryClient();

// Five-dot importance indicator as specified in design doc Section 3.1
export function ImportanceDots({ score, size = "md" }: { score: number; size?: "sm" | "md" | "lg" }) {
  const filled = Math.round(score * 5);
  const color =
    score >= 0.8
      ? "text-red-600"
      : score >= 0.6
      ? "text-orange-500"
      : score >= 0.4
      ? "text-amber-500"
      : "text-stone-400";
  const sizes = { sm: "text-xs gap-0.5", md: "text-sm gap-1", lg: "text-base gap-1" };
  return (
    <span className={`inline-flex items-center ${sizes[size]}`} title={`Importance: ${Math.round(score * 100)}%`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={i <= filled ? color : "text-stone-200 dark:text-stone-700"}>
          ●
        </span>
      ))}
    </span>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  const [darkMode, setDarkMode] = React.useState(false);

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    if (!darkMode) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  const navItems = [
    { to: "/", label: "Dashboard", icon: BookOpen },
    { to: "/papers", label: "Papers", icon: BarChart3 },
    { to: "/plan", label: "Study Plan", icon: Calendar },
    { to: "/revision", label: "Revision", icon: RotateCcw },
    { to: "/progress", label: "Coverage", icon: CheckCircle2 },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-[#FAFAF9] dark:bg-[#0C0A09] text-[#1C1917] dark:text-[#FAFAF9]">
      {/* Top Navbar */}
      <header className="sticky top-0 z-30 bg-white/80 dark:bg-[#1C1917]/80 backdrop-blur border-b border-[#E7E5E4] dark:border-[#44403C]">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <NavLink to="/" className="flex items-center gap-2 font-bold text-lg text-indigo-600 dark:text-indigo-400">
              <BookOpen className="w-5 h-5" />
              <span>CA Final Prep</span>
            </NavLink>
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-stone-100 dark:bg-stone-800 text-indigo-600 dark:text-indigo-400"
                        : "text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-900"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {isDemoMode() && (
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300">
                Demo Mode
              </span>
            )}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-orange-50 dark:bg-orange-950/40 text-orange-600 dark:text-orange-400 text-xs font-semibold">
              <Flame className="w-4 h-4 fill-orange-500" />
              <span>14d streak</span>
            </div>
            <button
              onClick={toggleDarkMode}
              className="p-2 rounded-lg text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              title="Toggle theme"
            >
              {darkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">{children}</main>
    </div>
  );
}

function DashboardView() {
  const data = demoDashboard;

  return (
    <div className="space-y-6">
      {/* Header banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-2xl bg-white dark:bg-[#1C1917] border border-[#E7E5E4] dark:border-[#44403C] shadow-sm">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Good day, {data.student_name}</h1>
          <p className="text-sm text-stone-500 mt-1">
            Exam target: <strong className="text-stone-800 dark:text-stone-200">{data.target_attempt}</strong> · {data.days_remaining} days remaining
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs uppercase tracking-wider font-semibold text-stone-400">Syllabus Coverage</div>
            <div className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">{data.overall_coverage_pct}%</div>
          </div>
          <div className="w-16 h-16 rounded-full border-4 border-indigo-100 dark:border-indigo-950 flex items-center justify-center font-bold text-sm text-indigo-600 dark:text-indigo-400">
            {data.completed_subtopics}/{data.total_subtopics}
          </div>
        </div>
      </div>

      {/* 3-Column Highlights */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Study Today */}
        <div className="p-5 rounded-xl bg-white dark:bg-[#1C1917] border border-[#E7E5E4] dark:border-[#44403C] space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-base">Study Today</h2>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400">
              3 prioritized
            </span>
          </div>
          <div className="space-y-3">
            {data.study_today.map((item) => (
              <div key={item.node_id} className="p-3 rounded-lg bg-stone-50 dark:bg-stone-900 border border-stone-200 dark:border-stone-800 space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-indigo-600 dark:text-indigo-400">{item.paper_code}</span>
                  <ImportanceDots score={item.importance} size="sm" />
                </div>
                <div className="font-medium text-sm line-clamp-1">{item.title}</div>
                <div className="flex items-center justify-between text-xs text-stone-500 pt-1">
                  <span>{item.estimated_minutes} mins</span>
                  <span className="capitalize">{item.status.replace("_", " ")}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Revision Due */}
        <div className="p-5 rounded-xl bg-white dark:bg-[#1C1917] border border-[#E7E5E4] dark:border-[#44403C] space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-base">Revision Due</h2>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-orange-50 dark:bg-orange-950 text-orange-600 dark:text-orange-400">
              {data.due_revision_count} due today
            </span>
          </div>
          <p className="text-sm text-stone-500">
            Spaced repetition intervals are active. Review these subtopics today to maintain retention.
          </p>
          <div className="p-4 rounded-lg bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-900/40 text-sm">
            <div className="font-semibold text-amber-900 dark:text-amber-200">Ind AS 116 — Lease Identification</div>
            <div className="text-xs text-amber-700 dark:text-amber-400 mt-1">Repetition #2 · Overdue by 1 day</div>
          </div>
          <NavLink
            to="/revision"
            className="block text-center w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-sm transition-colors"
          >
            Start Revision Queue →
          </NavLink>
        </div>

        {/* Papers Quick Access */}
        <div className="p-5 rounded-xl bg-white dark:bg-[#1C1917] border border-[#E7E5E4] dark:border-[#44403C] space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-base">Papers Overview</h2>
            <NavLink to="/papers" className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
              View all →
            </NavLink>
          </div>
          <div className="space-y-2">
            {[
              { code: "P1", name: "Financial Reporting", pct: 67 },
              { code: "P2", name: "Adv Financial Mgmt", pct: 64 },
              { code: "P3", name: "Adv Auditing", pct: 48 },
              { code: "P4", name: "Direct Tax Laws", pct: 53 },
            ].map((p) => (
              <div key={p.code} className="flex items-center justify-between text-sm py-1">
                <span className="font-medium text-stone-700 dark:text-stone-300">
                  <strong className="text-stone-900 dark:text-white mr-1.5">{p.code}</strong>
                  {p.name}
                </span>
                <span className="text-xs font-semibold text-stone-500">{p.pct}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<DashboardView />} />
            <Route
              path="/papers"
              element={
                <div className="p-6 bg-white dark:bg-[#1C1917] rounded-xl border border-[#E7E5E4] dark:border-[#44403C]">
                  <h1 className="text-xl font-bold mb-4">Papers Overview</h1>
                  <p className="text-stone-500 text-sm">Full papers list and taxonomy navigation.</p>
                </div>
              }
            />
            <Route
              path="/plan"
              element={
                <div className="p-6 bg-white dark:bg-[#1C1917] rounded-xl border border-[#E7E5E4] dark:border-[#44403C]">
                  <h1 className="text-xl font-bold mb-4">Study Plan</h1>
                  <p className="text-stone-500 text-sm">Day-by-day high-yield study schedule.</p>
                </div>
              }
            />
            <Route
              path="/revision"
              element={
                <div className="p-6 bg-white dark:bg-[#1C1917] rounded-xl border border-[#E7E5E4] dark:border-[#44403C]">
                  <h1 className="text-xl font-bold mb-4">Spaced Revision Queue</h1>
                  <p className="text-stone-500 text-sm">Flashcards and recall prompt reviews.</p>
                </div>
              }
            />
            <Route
              path="/progress"
              element={
                <div className="p-6 bg-white dark:bg-[#1C1917] rounded-xl border border-[#E7E5E4] dark:border-[#44403C]">
                  <h1 className="text-xl font-bold mb-4">Coverage Tracker</h1>
                  <p className="text-stone-500 text-sm">Syllabus completion metrics across chapters.</p>
                </div>
              }
            />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
