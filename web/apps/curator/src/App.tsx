import React from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { ListFilter, CheckCheck, FolderOpen, Activity, Network } from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient();

function CuratorLayout({ children }: { children: React.ReactNode }) {
  const navItems = [
    { to: "/queue", label: "Review Queue", icon: ListFilter, count: 18 },
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
              {item.count !== undefined && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-indigo-950/80 text-indigo-300 border border-indigo-700/50">
                  {item.count}
                </span>
              )}
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
            <span className="text-slate-200 font-semibold">12 units reviewed today</span>
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

function QueuePlaceholder() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">Unreviewed Classification Queue</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Review primary and secondary suggestion tags. Accepted decisions are published atomically to core.appearance.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 font-semibold text-xs transition-colors">
            Accept Current (A)
          </button>
          <button className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs transition-colors">
            Edit Node (E)
          </button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6 min-h-[500px]">
        {/* Unit Question/Answer Preview */}
        <div className="col-span-8 p-5 rounded-lg bg-[#1E293B] border border-[#334155] space-y-4">
          <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs px-2 py-0.5 rounded bg-indigo-950 border border-indigo-700 text-indigo-300 font-semibold">
                Unit #55
              </span>
              <span className="text-xs text-slate-300 font-medium">s2023.P1 · May 2024 · Q1(a)</span>
            </div>
            <span className="text-xs font-mono text-amber-400">10 Marks</span>
          </div>

          <div className="space-y-2">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Question Text</div>
            <div className="p-4 rounded bg-slate-900 border border-slate-800/80 text-xs font-mono leading-relaxed text-slate-200">
              FA Ltd. entered into a contract with customer ABC Ltd. to provide construction services for a consideration of ₹158 lakhs.
              Calculate the lease liability and right-of-use asset under Ind AS 116 as of 1st April 20X2 assuming incremental borrowing rate is 10%.
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Answer / Solution</div>
            <div className="p-4 rounded bg-slate-900 border border-slate-800/80 text-xs font-mono leading-relaxed text-slate-300">
              Present value of lease payments at 10% discount rate = ₹158 lakhs x 0.909 = ₹143.62 lakhs.
              Initial direct costs incurred by lessee = ₹4.5 lakhs.
              Total Right-of-Use Asset = ₹148.12 lakhs.
            </div>
          </div>
        </div>

        {/* Suggestion Panel */}
        <div className="col-span-4 p-5 rounded-lg bg-[#1E293B] border border-[#334155] space-y-4">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-700/60 pb-2">
            Classification Suggestions
          </div>

          <div className="p-3 rounded bg-emerald-950/40 border border-emerald-800/60 space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-emerald-400">Primary (Bucket A)</span>
              <span className="font-mono text-[10px] text-emerald-300">92% conf</span>
            </div>
            <div className="font-mono text-xs text-white font-bold">P1-BXTF71</div>
            <div className="text-xs text-slate-300">Initial measurement of ROU asset and lease liability</div>
            <div className="text-[10px] text-slate-400 pt-1 border-t border-emerald-900/60 font-mono">
              Evidence: "right-of-use asset", "lease liability", "Ind AS 116"
            </div>
          </div>

          <div className="space-y-1.5 pt-2">
            <div className="text-xs font-semibold text-slate-400">Secondary Suggestions</div>
            <div className="p-2.5 rounded bg-slate-900 border border-slate-800 text-xs space-y-1">
              <div className="font-mono text-[11px] text-indigo-400 font-semibold">P1-GDH25Q (64%)</div>
              <div className="text-[11px] text-slate-400">Identifying a lease contract and separating components</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/curator">
        <CuratorLayout>
          <Routes>
            <Route path="/" element={<QueuePlaceholder />} />
            <Route path="/queue" element={<QueuePlaceholder />} />
            <Route
              path="/bulk"
              element={
                <div className="p-6 bg-[#1E293B] rounded-lg border border-[#334155]">
                  <h1 className="text-base font-bold mb-2">Bulk Accept Bucket A</h1>
                  <p className="text-xs text-slate-400">Accept all high-confidence consensus suggestions per document.</p>
                </div>
              }
            />
            <Route
              path="/documents"
              element={
                <div className="p-6 bg-[#1E293B] rounded-lg border border-[#334155]">
                  <h1 className="text-base font-bold mb-2">Document Catalogue</h1>
                  <p className="text-xs text-slate-400">Manage ingested PDFs and metadata verification.</p>
                </div>
              }
            />
            <Route
              path="/taxonomy"
              element={
                <div className="p-6 bg-[#1E293B] rounded-lg border border-[#334155]">
                  <h1 className="text-base font-bold mb-2">Taxonomy Explorer</h1>
                  <p className="text-xs text-slate-400">Browse chapters, topics, subtopics, and descriptors.</p>
                </div>
              }
            />
            <Route
              path="/system"
              element={
                <div className="p-6 bg-[#1E293B] rounded-lg border border-[#334155]">
                  <h1 className="text-base font-bold mb-2">System Health & Alarms</h1>
                  <p className="text-xs text-slate-400">Monitor all 5 system alarms and model evaluation gates.</p>
                </div>
              }
            />
          </Routes>
        </CuratorLayout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
