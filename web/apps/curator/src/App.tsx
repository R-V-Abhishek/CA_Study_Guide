import React, { useSyncExternalStore } from "react";
import { authState, subscribeAuth } from "@caf/api-client";
import { AuthGate } from "./components/AuthGate";
import { SessionControls } from "./components/SessionControls";
import { Accounts } from "./pages/Accounts";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { ListFilter, CheckCheck, FolderOpen, Activity, Network, FileCheck } from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Queue } from "./pages/Queue";
import { ClassificationQueue } from "./pages/ClassificationQueue";
import { BulkAccept } from "./pages/BulkAccept";
import { Catalogue } from "./pages/Catalogue";
import { Taxonomy } from "./pages/Taxonomy";
import { TextbookExplorer } from "../../student/src/components/TextbookExplorer";
import { TaxonomyRelease } from "./pages/TaxonomyRelease";
import { Extraction } from "./pages/Extraction";
import { System } from "./pages/System";
import { Diagnostics } from "./components/Diagnostics";
import { RouteBoundary } from "./components/RouteBoundary";

const queryClient = new QueryClient();

function AdminOnly({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(subscribeAuth, authState);
  return state.identity?.capabilities.includes("admin") ? <>{children}</> : <p role="alert">Administrator access required.</p>;
}

function CuratorLayout({ children }: { children: React.ReactNode }) {
  const state = useSyncExternalStore(subscribeAuth, authState);
  const admin = state.identity?.capabilities.includes("admin");
  const navItems = [
    { to: "/classifications", label: "Question Classification", icon: ListFilter },
    { to: "/queue", label: "Review Queue", icon: ListFilter },
    { to: "/bulk", label: "Bulk Accept", icon: CheckCheck },
    { to: "/documents", label: "Catalogue", icon: FolderOpen },
    { to: "/extraction", label: "Extraction Review", icon: FileCheck },
    { to: "/taxonomy", label: "Taxonomy", icon: Network },
    { to: "/textbooks", label: "Textbook Taxonomy", icon: Network },
    { to: "/taxonomy-release", label: "Source & Release Review", icon: FileCheck },
    { to: "/system", label: "System Health", icon: Activity },
  ].filter(item => admin || ["/queue", "/classifications", "/taxonomy", "/textbooks", "/extraction"].includes(item.to));

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
              <div className="text-[10px] text-slate-400 font-mono">Classification review</div>
            </div>
          </div>
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
          <span className="text-slate-400">Curator workspace</span>
          <SessionControls /><Diagnostics />
        </header>

        <div className="flex-1 p-6 overflow-auto"><RouteBoundary>{children}</RouteBoundary></div>
      </main>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate><BrowserRouter basename="/curator">
        <CuratorLayout>
          <Routes>
            <Route path="/" element={<ClassificationQueue />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/classifications" element={<ClassificationQueue />} />
            <Route path="/bulk" element={<AdminOnly><BulkAccept /></AdminOnly>} />
            <Route path="/documents" element={<AdminOnly><Catalogue /></AdminOnly>} />
            <Route path="/extraction" element={<Extraction />} />
            <Route path="/taxonomy" element={<Taxonomy />} />
            <Route path="/textbooks" element={<TextbookExplorer curator />} />
            <Route path="/taxonomy-release" element={<AdminOnly><TaxonomyRelease /></AdminOnly>} />
            <Route path="/accounts" element={<AdminOnly><Accounts /></AdminOnly>} />
            <Route path="/system" element={<AdminOnly><System /></AdminOnly>} />
          </Routes>
        </CuratorLayout>
      </BrowserRouter></AuthGate>
    </QueryClientProvider>
  );
}

export default App;
