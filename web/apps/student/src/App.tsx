import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import {
  BookOpen,
  Calendar,
  CheckCircle2,
  RotateCcw,
  BarChart3,
  Moon,
  Sun,
  Flame,
} from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { isDemoMode } from "./lib/demo";
import { Dashboard } from "./pages/Dashboard";
import { Papers } from "./pages/Papers";
import { PaperDetail } from "./pages/PaperDetail";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 2, // 2 minutes cache
      refetchOnWindowFocus: false,
    },
  },
});

function Layout({ children }: { children: React.ReactNode }) {
  const [darkMode, setDarkMode] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("caf_theme");
      if (stored) return stored === "dark";
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }
    return false;
  });

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("caf_theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("caf_theme", "light");
    }
  }, [darkMode]);

  const navItems = [
    { to: "/", label: "Dashboard", icon: BookOpen },
    { to: "/papers", label: "Papers", icon: BarChart3 },
    { to: "/plan", label: "Study Plan", icon: Calendar },
    { to: "/revision", label: "Revision", icon: RotateCcw },
    { to: "/progress", label: "Coverage", icon: CheckCircle2 },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-[#FAFAF9] dark:bg-[#0C0A09] text-[#1C1917] dark:text-[#FAFAF9] transition-colors duration-150">
      {/* Top Navbar */}
      <header className="sticky top-0 z-30 bg-white/90 dark:bg-[#1C1917]/90 backdrop-blur border-b border-[#E7E5E4] dark:border-[#44403C]">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <NavLink
              to="/"
              className="flex items-center gap-2 font-black text-lg tracking-tight text-indigo-600 dark:text-indigo-400"
            >
              <BookOpen className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
              <span>CA Final Prep</span>
            </NavLink>

            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      isActive
                        ? "bg-indigo-50 dark:bg-stone-800 text-indigo-600 dark:text-indigo-400"
                        : "text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60"
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
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-900 dark:bg-amber-950/80 dark:text-amber-300 border border-amber-300/50">
                Demo Mode
              </span>
            )}
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-orange-100 dark:bg-orange-950/50 text-orange-700 dark:text-orange-400 text-xs font-bold">
              <Flame className="w-4 h-4 fill-orange-500 text-orange-500" />
              <span>14d streak</span>
            </div>
            <button
              type="button"
              onClick={() => setDarkMode(!darkMode)}
              className="p-2 rounded-xl text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
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

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/papers" element={<Papers />} />
            <Route path="/papers/:paperId" element={<PaperDetail />} />
            <Route path="/papers/:paperId/:nodeId" element={<PaperDetail />} />
            <Route
              path="/plan"
              element={
                <div className="p-8 bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 max-w-2xl mx-auto text-center space-y-3">
                  <div className="p-3 w-fit mx-auto rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
                    <Calendar className="w-6 h-6" />
                  </div>
                  <h1 className="text-xl font-bold text-stone-900 dark:text-white">
                    Study Plan (Phase 3)
                  </h1>
                  <p className="text-xs text-stone-500 leading-relaxed">
                    Automated high-yield weekly schedule will generate day-by-day study tasks based on exam weightage and weak areas.
                  </p>
                </div>
              }
            />
            <Route
              path="/revision"
              element={
                <div className="p-8 bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 max-w-2xl mx-auto text-center space-y-3">
                  <div className="p-3 w-fit mx-auto rounded-xl bg-orange-50 dark:bg-orange-950/60 text-orange-600 dark:text-orange-400">
                    <RotateCcw className="w-6 h-6" />
                  </div>
                  <h1 className="text-xl font-bold text-stone-900 dark:text-white">
                    Spaced Revision Queue (Phase 3)
                  </h1>
                  <p className="text-xs text-stone-500 leading-relaxed">
                    Flashcard review queue implementing Leitner/spaced-repetition intervals (3, 7, 21, 60 days) to prevent forgetting curves.
                  </p>
                </div>
              }
            />
            <Route
              path="/progress"
              element={
                <div className="p-8 bg-white dark:bg-stone-900 rounded-2xl border border-stone-200 dark:border-stone-800 max-w-2xl mx-auto text-center space-y-3">
                  <div className="p-3 w-fit mx-auto rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <h1 className="text-xl font-bold text-stone-900 dark:text-white">
                    Full Coverage Overview (Phase 3)
                  </h1>
                  <p className="text-xs text-stone-500 leading-relaxed">
                    Deep multi-paper syllabus completion breakdown and mock test score tracking.
                  </p>
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
