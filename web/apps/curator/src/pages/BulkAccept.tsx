import { accountKey, authGeneration, classificationApi, type ClassificationReview } from "@caf/api-client";
import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RequestError } from "../components/RequestError";
import { QuestionParts, Answers, LabelPath } from "../components/ClassificationContext";

export function BulkAccept() {
  const cache = useQueryClient();
  const generation = authGeneration();
  const [selected, setSelected] = useState<number[]>([]);
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const submitting = useRef(false);
  const retry = useRef<{ signature: string; keys: Record<number, string> } | null>(null);
  const queue = useQuery({ queryKey: ["classification-bulk", accountKey()], queryFn: () => classificationApi.queue({ limit: "500" }) });
  const chosen = queue.data?.filter(item => selected.includes(item.suggestion_revision_id)) ?? [];
  const bulk = useMutation({ mutationFn: () => {
    const signature = JSON.stringify({ selected, note, publications: chosen.map(item => item.publication_revision_id) });
    if (retry.current?.signature !== signature) retry.current = { signature, keys: Object.fromEntries(selected.map(id => [id, crypto.randomUUID()])) };
    const reviews: ClassificationReview[] = chosen.map(item => ({ expected_suggestion_revision_id: item.suggestion_revision_id, expected_publication_revision_id: item.publication_revision_id, idempotency_key: retry.current!.keys[item.suggestion_revision_id], mappings: item.mappings, note, blind: false }));
    return classificationApi.bulk(reviews);
  }, onSuccess: async result => {
    if (generation !== authGeneration()) return;
    setMessage(`Published ${result.revisions.length} explicitly reviewed classification revisions.`);
    setSelected([]); setConfirmed(false); retry.current = null;
    await cache.invalidateQueries({ queryKey: ["classification-bulk"] });
    await cache.invalidateQueries({ queryKey: ["classification-queue"] });
  }, onSettled: () => { submitting.current = false; } });
  const eligible = chosen.length === selected.length && chosen.every(item => item.publication_ready && !item.stale && !item.experimental && !item.dispute_status && item.mappings.every(part => part.outcome !== "needs_review" || part.excluded));
  return <div className="space-y-4 max-w-5xl"><h1 className="text-xl font-bold">Bulk review</h1><p className="text-sm">Select the exact root revisions you reviewed. Model confidence and buckets do not authorize publication.</p>
    <RequestError error={queue.error} retry={() => void queue.refetch()} /><RequestError error={bulk.error} />{message && <p role="status">{message}</p>}
    {queue.isPending ? <p role="status">Loading classification revisions…</p> : queue.isError ? null : !queue.data?.length ? <p>No classification suggestions available.</p> : queue.data.map(item => <section key={item.suggestion_revision_id} className="rounded-xl border border-slate-700 bg-slate-800 p-4 space-y-2"><label><input type="checkbox" aria-label={`Select suggestion revision ${item.suggestion_revision_id}`} checked={selected.includes(item.suggestion_revision_id)} disabled={!item.publication_ready || item.stale || item.experimental || !!item.dispute_status || bulk.isPending} onChange={event => { setSelected(values => event.target.checked ? [...values, item.suggestion_revision_id] : values.filter(id => id !== item.suggestion_revision_id)); setConfirmed(false); setMessage(""); }} /> Suggestion revision {item.suggestion_revision_id} · {item.paper_id} · {item.question.display_label} · published revision {item.publication_revision_id ?? "none"}</label><p className="text-xs">Extraction {item.extraction_revision_id} · taxonomy {item.taxonomy_version_id}</p>{item.readiness_blockers.map(block => <p className="text-sm text-amber-200" key={block.code}>{block.message}</p>)}<details><summary>Review whole question, answer and every part label</summary><p className="whitespace-pre-wrap">{item.question.common_stem}</p><p className="whitespace-pre-wrap">{item.question.question_text}</p><QuestionParts parts={item.question.parts} /><h3 className="font-semibold">Available answer · {item.question.answer_status}</h3>{item.question.answers.length ? <Answers parts={item.question.answers} /> : <p>Answer unavailable</p>}<h3 className="font-semibold">Complete part labels</h3>{item.mappings.map(part => <div key={part.part_id} className="border-l border-slate-600 pl-3"><p>{part.part_id.split(":").slice(1).join(":") || item.question.display_label} · {part.excluded ? "Excluded" : part.outcome}</p>{part.primary_node_id && <p>Primary: <LabelPath id={part.primary_node_id} item={item} /></p>}{(part.secondary_node_ids ?? []).map(id => <p key={id}>Secondary: <LabelPath id={id} item={item} /></p>)}</div>)}</details></section>)}
    <label className="block">Review evidence<textarea aria-label="Bulk review evidence" className="block w-full bg-slate-900 border border-slate-600 p-2" maxLength={10000} value={note} onChange={event => setNote(event.target.value)} /></label><label><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /> I reviewed the complete question, available answer and all labels for every selected revision</label><button className="block rounded bg-emerald-700 px-4 py-3 disabled:opacity-50" disabled={!selected.length || !eligible || !confirmed || !note.trim() || bulk.isPending} onClick={() => { if (submitting.current) return; submitting.current = true; bulk.mutate(); }}>Publish {selected.length} selected revisions</button>
  </div>;
}
