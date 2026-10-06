import { accountKey, authGeneration } from "@caf/api-client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { tinykeys } from "tinykeys";
import type { components } from "@caf/api-client";
import { NodePickerModal } from "../components/NodePickerModal";
import { RequestError } from "../components/RequestError";
import { curatorClient, requiredData } from "../lib/client";

type Recommendation = components["schemas"]["CuratorRecommendation"];
type DecisionAction = components["schemas"]["DecisionRequest"]["action"];

function RecommendationPath({ recommendation }: { recommendation: Recommendation }) {
  const ancestry = recommendation.breadcrumbs?.length ? recommendation.breadcrumbs : [recommendation.module, recommendation.chapter, recommendation.unit, recommendation.topic, recommendation.subtopic].filter(Boolean);
  return <div className="space-y-1">
    <p className="text-xs text-slate-400">{ancestry.map(node => node!.name).join(" → ") || "Ancestry unavailable"}</p>
    <p className="text-sm font-semibold">{recommendation.node_name ?? "Name unavailable"}</p>
    <p className="text-xs font-mono text-indigo-300">{recommendation.node_id}</p>
  </div>;
}

export function Queue() {
  const accountId = accountKey();
  const generation = authGeneration();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const bucket = params.get("bucket") ?? "all";
  const paper = params.get("paper") ?? "all";
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [answerExpanded, setAnswerExpanded] = useState(false);
  const startTime = useRef(Date.now());
  const submitting = useRef(false);
  const activeFilters = useRef({ bucket, paper });
  activeFilters.current = { bucket, paper };
  const queue = useQuery({
    queryKey: ["curator-queue", accountKey(), bucket, paper],
    queryFn: async () => requiredData(await curatorClient.GET("/api/v1/curate/queue", {
      params: { query: { ...(bucket !== "all" ? { bucket } : {}), ...(paper !== "all" ? { paper_id: paper } : {}) } },
    })),
  });
  const papers = useQuery({ queryKey: ["curator-papers", accountKey()], queryFn: async () => requiredData(await curatorClient.GET("/api/v1/papers")) });
  const items = queue.data ?? [];
  const index = Math.max(0, items.findIndex(item => item.unit_id === selectedId));
  const unit = items[index];

  useEffect(() => { setSelectedId(null); setPickerOpen(false); }, [bucket, paper]);
  useEffect(() => {
    setSelectedId(current => items.some(item => item.unit_id === current) ? current : items[0]?.unit_id ?? null);
  }, [items]);
  useEffect(() => { startTime.current = Date.now(); setAnswerExpanded(false); }, [unit?.unit_id]);

  const decision = useMutation({
    mutationFn: async ({ action, nodeId, unitId }: { action: DecisionAction; nodeId: string | null; unitId: number; bucket: string; paper: string }) => requiredData(await curatorClient.POST("/api/v1/curate/units/{unit_id}/decision", {
      params: { path: { unit_id: unitId } },
      body: { action, primary_node_id: nodeId, secondary_node_ids: [], seconds_spent: Math.max(1, (Date.now() - startTime.current) / 1000), blind: false },
    })),
    onSuccess: async (_, variables) => {
      if (generation !== authGeneration()) return;
      const key = ["curator-queue", accountId, variables.bucket, variables.paper];
      const currentItems = queryClient.getQueryData<typeof items>(key) ?? [];
      const acceptedIndex = currentItems.findIndex(item => item.unit_id === variables.unitId);
      const remaining = currentItems.filter(item => item.unit_id !== variables.unitId);
      queryClient.setQueryData(key, remaining);
      if (activeFilters.current.bucket === variables.bucket && activeFilters.current.paper === variables.paper) {
        setSelectedId(remaining[Math.min(Math.max(0, acceptedIndex), remaining.length - 1)]?.unit_id ?? null);
        setPickerOpen(false);
      }
      await queryClient.invalidateQueries();
    },
    onSettled: () => { submitting.current = false; },
  });
  const submit = (action: DecisionAction, nodeId?: string) => {
    if (!unit || submitting.current) return;
    if (unit.publication_ready === false && action !== "none_fits" && action !== "exclude") return;
    submitting.current = true;
    decision.mutate({ action, bucket, paper, unitId: unit.unit_id, nodeId: action === "exclude" || action === "none_fits" ? null : nodeId ?? unit.primary_suggestion.node_id });
  };
  const move = (offset: number) => {
    if (!submitting.current && items[index + offset]) { decision.reset(); setSelectedId(items[index + offset].unit_id); }
  };
  const filter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    value === "all" ? next.delete(name) : next.set(name, value);
    decision.reset(); setParams(next);
  };
  useEffect(() => {
    if (pickerOpen) return;
    const shortcut = (callback: () => void) => (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName) || target.isContentEditable) return;
      event.preventDefault(); callback();
    };
    return tinykeys(window, {
      a: shortcut(() => submit("accept")), e: shortcut(() => { if (unit && unit.publication_ready !== false && !submitting.current) setPickerOpen(true); }),
      n: shortcut(() => submit("none_fits")), x: shortcut(() => submit("exclude")),
      ArrowRight: shortcut(() => move(1)), l: shortcut(() => move(1)),
      ArrowLeft: shortcut(() => move(-1)), h: shortcut(() => move(-1)),
    });
  }, [unit, index, items, pickerOpen]);

  return <div className="space-y-4">
    <p className="text-sm text-amber-200">Historical suggestion evidence has an unknown verification state. <a className="underline" href="/curator/classifications">Open whole question classification to review an immutable root revision.</a></p>
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-700 pb-3">
      <h1 className="font-bold mr-auto">Review Queue</h1>
      <label className="text-xs">Bucket <select aria-label="Bucket" value={bucket} disabled={decision.isPending} onChange={e => filter("bucket", e.target.value)} className="ml-2 bg-slate-900 rounded p-2">
        <option value="all">All Buckets</option>{["A", "B", "C", "D"].map(value => <option key={value} value={value}>Bucket {value}</option>)}
      </select></label>
      <label className="text-xs">Paper <select aria-label="Paper" value={paper} disabled={decision.isPending || papers.isPending} onChange={e => filter("paper", e.target.value)} className="ml-2 bg-slate-900 rounded p-2">
        <option value="all">All Papers</option>{papers.data?.map(item => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}
        {paper !== "all" && !papers.data?.some(item => item.id === paper) && <option value={paper}>{paper}</option>}
      </select></label>
      <button aria-label="Previous unit" onClick={() => move(-1)} disabled={index === 0 || decision.isPending}>←</button>
      <span className="text-xs">{items.length ? index + 1 : 0} / {items.length}</span>
      <button aria-label="Next unit" onClick={() => move(1)} disabled={index >= items.length - 1 || decision.isPending}>→</button>
    </div>
    <RequestError error={papers.error} retry={() => void papers.refetch()} />
    <RequestError error={queue.error} retry={() => void queue.refetch()} />
    <RequestError error={decision.error} />
    {queue.isPending ? <p role="status">Loading review queue…</p> : queue.isError ? null : !unit ? <div className="p-10 text-center bg-slate-800 rounded-xl">
      <h2 className="font-bold">{bucket !== "all" || paper !== "all" ? "No units match these filters" : "Queue Empty"}</h2>
      <p className="text-sm text-slate-400 mt-2">{bucket !== "all" || paper !== "all" ? "Change the paper or bucket to see other pending units." : "There are no pending review units."}</p>
    </div> : <div className="grid lg:grid-cols-3 gap-5">
      <div className="lg:col-span-2 bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-5">
        <p className="text-sm">Unit #{unit.unit_id} · {unit.paper_id} · {unit.attempt_id} · {unit.display_label} ({unit.label_path}) {unit.marks !== null && `· ${unit.marks} Marks`}</p>
        <p className="text-xs text-amber-200">Historical topic verification state: unknown.{unit.requires_re_review && ' Classification provenance requires re-review.'}</p>
        <section><h2 className="text-xs font-bold mb-2">Question Text</h2><div tabIndex={0} role="region" aria-label="Question text" className="p-4 bg-slate-900 rounded whitespace-pre-wrap text-xs max-h-80 overflow-auto">{unit.question_text || "Question text unavailable"}</div></section>
        <section><h2 className="text-xs font-bold mb-2">Model Solution / Answer</h2>
          {unit.answer_text === null ? <p className="text-sm text-amber-300">Answer unavailable</p> : <>
            <div tabIndex={0} role="region" aria-label="Answer text" className={`p-4 bg-slate-900 rounded whitespace-pre-wrap text-xs overflow-auto ${answerExpanded ? "" : "max-h-80"}`}>{unit.answer_text || "The returned answer is empty."}</div>
            <button type="button" aria-expanded={answerExpanded} className="text-xs underline mt-2" onClick={() => setAnswerExpanded(value => !value)}>{answerExpanded ? "Collapse answer" : "Expand full answer"}</button>
          </>}
        </section>
      </div>
      <div className="space-y-4">
        <section className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-3">
          <h2 className="font-bold text-sm">Classifier Recommendation · Bucket {unit.bucket}</h2>
          <RecommendationPath recommendation={unit.primary_suggestion} />
          {unit.primary_suggestion.justification && <p className="text-xs whitespace-pre-wrap text-slate-300">{unit.primary_suggestion.justification}</p>}
          {unit.secondary_suggestions.map(item => <button key={item.node_id} disabled={decision.isPending || unit.publication_ready === false} onClick={() => submit("edit", item.node_id)} className="p-3 w-full text-left rounded border border-slate-700"><RecommendationPath recommendation={item} /><span className="text-xs underline">Choose candidate</span></button>)}
        </section>
        <section className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-3">
          {unit.publication_ready === false && <p className="text-sm text-amber-200">These textbook suggestions await publication review. Your saved historical labels are preserved.</p>}
          <button onClick={() => submit("accept")} disabled={decision.isPending || unit.publication_ready === false} className="w-full rounded bg-emerald-600 p-3 text-sm font-bold disabled:opacity-50">{decision.isPending ? "Saving decision…" : "[A] Accept Recommendation"}</button>
          <button onClick={() => setPickerOpen(true)} disabled={decision.isPending || unit.publication_ready === false} className="w-full rounded bg-slate-700 p-3 text-sm">[E] Reclassify (Choose Node)</button>
          <div className="flex gap-2"><button onClick={() => submit("none_fits")} disabled={decision.isPending} className="flex-1 rounded bg-slate-900 p-3 text-xs">[N] None Fits</button><button onClick={() => submit("exclude")} disabled={decision.isPending} className="flex-1 rounded bg-slate-900 p-3 text-xs text-rose-300">[X] Exclude</button></div>
        </section>
      </div>
    </div>}
    <NodePickerModal isOpen={pickerOpen && !decision.isPending} onClose={() => setPickerOpen(false)} onSelect={id => submit("edit", id)} currentSelectedId={unit?.primary_suggestion.node_id} />
  </div>;
}
