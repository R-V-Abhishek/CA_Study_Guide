import React from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { ListFilter, CheckCheck, FolderOpen, Activity, Network } from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Queue } from "./pages/Queue";
import { BulkAccept } from "./pages/BulkAccept";
import { Catalogue } from "./pages/Catalogue";
import { Taxonomy } from "./pages/Taxonomy";
import { System } from "./pages/System";

const queryClient = new QueryClient();

function CuratorLayout({ children }: { children: React.ReactNode }) {
  const navItems = [
    { to: "/queue", label: "Review Queue", icon: ListFilter },
    { to: "/bulk", label: "Bulk Accept", icon: CheckCheck },
    { to: "/documents", label: "Catalogue", icon: FolderOpen },
    { to: "/taxonomy", label: "Taxonomy", icon: Network },
    { to: "/system", label: "System Health", icon: Activity },
  ];

  return (
    <div className="min-h-screen flex bg-[#0F172A] text-[#F8FAFC]">
      {/* Left Sidebar */}
      <aside className="w-64 border-r border-[#334155] bg-[#1E293B]/50 flex flex-col shrink-0">
        <div className="p-4 border-b border-[#334155] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded bg-indigo-600 flex items-center justify-center font-black text-xs">
              CA
            </div>
            <div>
              <div className="font-bold text-sm leading-tight">Curator Tool</div>
              <div className="text-[10px] text-slate-400 font-mono">v2.0 · target 2026-05</div>
            </div>
          </div>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-950 border border-emerald-800 text-emerald-400">
            ONLINE
          </span>
        </div>

        <nav className="p-2 space-y-0.5 flex-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-indigo-600 text-white font-semibold"
                    : "text-slate-300 hover:bg-[#334155]/60 hover:text-white"
                }`
              }
            >
              <div className="flex items-center gap-2.5">
                <item.icon className="w-4 h-4" />
                <span>{item.label}</span>
              </div>
            </NavLink>
          ))}
        </nav>

        {/* Shortcuts reminder */}
        <div className="p-3 m-2 rounded bg-slate-900/60 border border-slate-800 text-[11px] text-slate-400 space-y-1 font-mono">
          <div className="font-sans font-semibold text-slate-300 text-xs flex items-center gap-1.5">
            <span>Keyboard Shortcuts</span>
          </div>
          <div className="flex justify-between">
            <span>[A] Accept</span>
            <span>[E] Edit Node</span>
          </div>
          <div className="flex justify-between">
            <span>[N] None Fits</span>
            <span>[X] Exclude</span>
          </div>
          <div className="flex justify-between">
            <span>[→/L] Next</span>
            <span>[←/H] Prev</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-12 border-b border-[#334155] px-6 flex items-center justify-between bg-[#1E293B]/20 text-xs">
          <div className="flex items-center gap-2 text-slate-400 font-mono">
            <span>SESSION:</span>
            <span className="text-slate-200 font-semibold">Ready</span>
            <span>·</span>
            <span>BUCKET A PRECISION:</span>
            <span className="text-emerald-400 font-semibold">100.0%</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-slate-400">Press <kbd className="px-1 py-0.5 rounded bg-slate-800 border border-slate-700 font-mono text-[10px]">?</kbd> for help</span>
          </div>
        </header>

        <div className="flex-1 p-6 overflow-auto">{children}</div>
      </main>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/curator">
        <CuratorLayout>
          <Routes>
            <Route path="/" element={<Queue />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/bulk" element={<BulkAccept />} />
            <Route path="/documents" element={<Catalogue />} />
            <Route path="/taxonomy" element={<Taxonomy />} />
            <Route path="/system" element={<System />} />
          </Routes>
        </CuratorLayout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
