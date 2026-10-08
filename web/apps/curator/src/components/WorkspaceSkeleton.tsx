export function WorkspaceSkeleton({ label }: { label: string }) {
  return <div aria-busy="true" aria-label={label} className="space-y-4"><p role="status">{label}</p>{[0, 1, 2].map(row => <div key={row} className="rounded-xl border border-slate-700 p-4 space-y-3"><div aria-hidden="true" className="h-5 w-2/3 bg-slate-800 rounded animate-pulse" /><div aria-hidden="true" className="h-3 w-full bg-slate-800 rounded animate-pulse" /><div aria-hidden="true" className="h-3 w-3/4 bg-slate-800 rounded animate-pulse" /></div>)}</div>;
}
