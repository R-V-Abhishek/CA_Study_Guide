import { accountKey } from "@caf/api-client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { curatorClient, requiredData } from "../lib/client";
import { RequestError } from "../components/RequestError";

export function System() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [targetAttempt, setTargetAttempt] = useState('2027-05');
  const health = useQuery({ queryKey: ["curator-system-health", accountKey()], queryFn: async () => requiredData(await curatorClient.GET("/api/v1/system/health")) });
  const backups = useQuery({ queryKey: ["curator-system-backups", accountKey()], queryFn: async () => requiredData(await curatorClient.GET("/api/v1/system/backups")) });
  const recompute = useMutation({
    mutationFn: async () => requiredData(await curatorClient.POST("/api/v1/curate/intel/recompute", { params: { query: { target_attempt_id: targetAttempt } } })),
    onSuccess: async () => {
      setMessage(`Score recompute completed. `);
      await queryClient.invalidateQueries();
    },
  });
  return <div className="max-w-5xl mx-auto space-y-6">
    <h1 className="page-title">System</h1><p>Inspect operational health and backups, and recompute scores for the selected attempt.</p><div className="flex flex-wrap gap-3 items-center justify-between border-b border-slate-700 pb-4">
      <h2 className="font-semibold">Processing</h2>
      <label>Scoring target <input aria-label="Scoring target" className="bg-slate-800 rounded p-2" value={targetAttempt} onChange={event => setTargetAttempt(event.target.value)} /></label>
      <button disabled={recompute.isPending} onClick={() => { if (!recompute.isPending) { setMessage(null); recompute.mutate(); } }} className="bg-indigo-600 rounded-xl px-4 py-2 text-sm disabled:opacity-50">{recompute.isPending ? "Recomputing…" : "Refresh historical scores"}</button>
    </div>
    <RequestError error={recompute.error} />
    {message && <p role="status" className="text-emerald-300">{message}</p>}
    <RequestError error={health.error} retry={() => void health.refetch()} />
    {health.isPending ? <p role="status">Loading system health…</p> : health.data && <>
      <section className="bg-slate-800 rounded-xl border border-slate-700 p-6">
        <h2 className="text-xs text-slate-400">Service health</h2>
        <p className="text-xl font-bold mt-2">{health.data.status}</p>
        <p className="text-xs text-slate-400 mt-2">Last evaluated: {new Date(health.data.evaluated_at).toLocaleString()}</p>
      </section>
      <section className="space-y-3"><h2 className="font-bold">Operational alarms</h2>
        {health.data.alarms.length === 0 ? <p className="text-sm text-slate-400">No operational alarms returned.</p> : health.data.alarms.map(alarm => <div key={alarm.code} className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-2">
          <p className="font-mono text-xs">{alarm.code} · {alarm.level}</p><p className="text-sm">{alarm.message}</p>
        </div>)}
      </section>
    </>}
    <section className="bg-slate-800 rounded-xl border border-slate-700 p-5 space-y-4">
      <h2 className="font-bold">Recovery and backups</h2>
      <RequestError error={backups.error} retry={() => void backups.refetch()} />
      {backups.isPending ? <p role="status">Loading backups…</p> : backups.data && <>
        <p className="text-sm text-slate-400">{backups.data.count} snapshots</p>
        {backups.data.backups.length === 0 ? <p className="text-sm text-slate-400">No backup snapshots returned.</p> : backups.data.backups.map(backup => <div key={backup.name} className="flex flex-wrap justify-between gap-2 text-xs border-t border-slate-700 pt-3">
          <span>{backup.name}</span><span>{backup.size_mb.toFixed(2)} MB · {new Date(backup.created_at).toLocaleString()}</span>
        </div>)}
      </>}
    </section>
  </div>;
}
