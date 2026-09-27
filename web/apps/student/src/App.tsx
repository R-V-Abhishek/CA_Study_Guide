import { useState, useEffect } from "react";
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
  FileCheck,
} from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { isDemoMode } from "./lib/demo";
import { Dashboard } from "./pages/Dashboard";
import { Papers } from "./pages/Papers";
import { PaperDetail } from "./pages/PaperDetail";
import { Plan } from "./pages/Plan";
import { Revision } from "./pages/Revision";
import { Progress } from "./pages/Progress";
import { MockTests } from "./pages/MockTests";

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
    { to: "/mock", label: "Mock Tests", icon: FileCheck },
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
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6 pb-20 md:pb-6">{children}</main>

      {/* Mobile Bottom Navigation Bar (md:hidden) */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-30 bg-white/95 dark:bg-[#1C1917]/95 backdrop-blur border-t border-[#E7E5E4] dark:border-[#44403C] flex items-center justify-around py-2 px-1">
        {navItems.slice(0, 5).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 px-2 py-1 rounded-lg text-[10px] font-semibold transition-colors ${
                isActive
                  ? "text-indigo-600 dark:text-indigo-400"
                  : "text-stone-500 hover:text-stone-800 dark:hover:text-stone-200"
              }`
            }
          >
            <item.icon className="w-4 h-4" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
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
            <Route path="/plan" element={<Plan />} />
            <Route path="/revision" element={<Revision />} />
            <Route path="/progress" element={<Progress />} />
            <Route path="/mock" element={<MockTests />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
