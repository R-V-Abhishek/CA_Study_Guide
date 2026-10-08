import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accountKey, authGeneration, authState, subscribeAuth, classificationApi, ApiError, type PartMapping } from "@caf/api-client";
import { extractionApi } from "@caf/api-client/src/extraction";
import { QuestionParts, Answers, LabelPath, MappingEvidence, MappingSummary, type Candidate } from "../components/ClassificationContext";
import { ExtractionEvidence } from "../components/ExtractionEvidence";
import { NodePickerModal } from "../components/NodePickerModal";
import { RequestError } from "../components/RequestError";
import { WorkspaceSkeleton } from "../components/WorkspaceSkeleton";

import { ReviewWorkspace, type ReviewTab } from "../components/ReviewWorkspace";

const panel = "bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3";
const control = "rounded bg-slate-900 border border-slate-600 p-2 text-sm disabled:opacity-50";

export function ClassificationQueue() {
  const cache = useQueryClient();
  const admin = !!useSyncExternalStore(subscribeAuth, authState).identity?.capabilities.includes("admin");
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<number | null>(null);
  const [mappings, setMappings] = useState<PartMapping[]>([]);
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [picker, setPicker] = useState<{ part: string; secondary: boolean } | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [tab, setTab] = useState<ReviewTab>("Question");
  const [activePart, setActivePart] = useState<string | null>(null);
  const conflictDialog = useRef<HTMLDialogElement>(null);
  const [message, setMessage] = useState("");
  const retryKey = useRef<{ signature: string; key: string } | null>(null);
  const submitting = useRef(false);
  const generation = authGeneration();
  const blind = params.get("blind") === "true";
  const queue = useQuery({ queryKey: ["classification-queue", accountKey(), params.toString()], queryFn: () => classificationApi.queue(Object.fromEntries(params.entries())) });
  const items = queue.data ?? [];
  const index = Math.max(0, items.findIndex(item => item.suggestion_revision_id === selected));
  const item = items[index];
  useEffect(() => { setSelected(null); }, [params.toString()]);
  useEffect(() => {
    setMappings(item?.mappings.map(part => ({ ...part, secondary_node_ids: [...(part.secondary_node_ids ?? [])] })) ?? []);
    setNote(""); setConfirmed(false); setPicker(null); setShowHistory(false); retryKey.current = null;
  }, [item?.suggestion_revision_id, blind]);
  const history = useQuery({ queryKey: ["classification-history", accountKey(), item?.question_id], queryFn: () => classificationApi.history(item!.question_id), enabled: !!item && showHistory });
  const disputes = useQuery({ queryKey: ["classification-disputes", accountKey(), item?.question_id], queryFn: () => classificationApi.disputes(item!.question_id), enabled: !!item && !!item.dispute_status });
  const extraction = useQuery({ queryKey: ["classification-extraction", accountKey(), item?.extraction_revision_id], queryFn: () => extractionApi.revision(item!.extraction_revision_id), enabled: !!item && evidenceOpen });
  const mutation = useMutation({ mutationFn: async (action: "review" | "verify" | "withdraw" | "dispute" | "dismiss" | "replace") => {
    if (!item) throw new Error("Select a question");
    const signature = JSON.stringify({ action, suggestion: item.suggestion_revision_id, publication: item.publication_revision_id, mappings, note, blind });
    if (retryKey.current?.signature !== signature) retryKey.current = { signature, key: crypto.randomUUID() };
    const expected = { expected_suggestion_revision_id: action === "verify" || action === "withdraw" || action === "dismiss" ? item.publication_suggestion_revision_id ?? item.suggestion_revision_id : item.suggestion_revision_id, expected_publication_revision_id: item.publication_revision_id, idempotency_key: retryKey.current.key };
    if (action === "review") return classificationApi.review(item.suggestion_revision_id, { ...expected, mappings, note, blind });
    if (action === "verify") return classificationApi.verify(item.question_id, expected);
    if (action === "withdraw") return classificationApi.withdraw(item.question_id, expected);
    if (action === "dispute") return classificationApi.dispute(item.question_id, { ...expected, reason: note, replacement_mappings: mappings });
    const open = disputes.data?.find(dispute => dispute.status === "open");
    if (!open) throw new Error("Refresh the current dispute before resolving");
    return classificationApi.resolve(open.id, { ...expected, resolution: action, reason: note, ...(action === "replace" ? { replacement_mappings: mappings } : {}) });
  }, onSuccess: async result => {
    if (generation !== authGeneration()) return;
    if (blind) { const next = new URLSearchParams(params); next.delete("blind"); setParams(next); }
    setMessage(blind ? "Blind benchmark saved; suggestions are now visible. Publication and student verification are unchanged." : result.pending ? "Replacement saved for explicit review. The previous publication remains visible." : "Revision operation saved.");
    setConfirmed(false); retryKey.current = null;
    for (const key of ["classification-queue", "classification-history", "classification-disputes"]) await cache.invalidateQueries({ queryKey: [key] });
  }, onError: error => { if ((error as ApiError).status === 409) { setConfirmed(false); conflictDialog.current?.showModal(); } }, onSettled: () => { submitting.current = false; } });
  const submit = (action: "review" | "verify" | "withdraw" | "dispute" | "dismiss" | "replace") => { if (submitting.current) return; submitting.current = true; mutation.mutate(action); };
  const update = (part: string, patch: Partial<PartMapping>) => {
    setMappings(current => current.map(value => value.part_id === part ? { ...value, ...patch, evidence: {}, confidence: null, bucket: null } : value));
    setConfirmed(false); mutation.reset();
  };
  const filter = (name: string, value: string) => { const next = new URLSearchParams(params); if (name !== "offset") next.delete("offset"); value ? next.set(name, value) : next.delete(name); setParams(next); mutation.reset(); setMessage(""); };
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (!event.altKey || (event.target as HTMLElement).closest("input, textarea, select, [contenteditable=true]")) return;
      const key = event.key.toLowerCase();
      if (key === "j" && index < items.length - 1 && !mutation.isPending) setSelected(items[index + 1].suggestion_revision_id);
      else if (key === "k" && index > 0 && !mutation.isPending) setSelected(items[index - 1].suggestion_revision_id);
      else if (["q", "a", "l"].includes(key)) setTab(key === "q" ? "Question" : key === "a" ? "Answer" : "Labels");
      else return;
      event.preventDefault();
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [index, items, mutation.isPending]);
  const selectPart = (id: string) => { setActivePart(id); document.getElementById(`mapping-${id}`)?.scrollIntoView({ block: "center", behavior: "auto" }); };
  const unresolved = mappings.some(part => part.outcome === "needs_review" && !part.excluded);
  const filterOptions: { name: string; label: string; options: [string, string][] }[] = [
    { name: "outcome", label: "Outcome", options: [["matched", "Matched"], ["needs_review", "Needs review"], ["none_fits", "None fits"]] },
    { name: "experimental", label: "Experimental", options: [["true", "Experimental"], ["false", "Reviewed inputs"]] },
    { name: "ready", label: "Readiness", options: [["true", "Ready"], ["false", "Blocked"]] },
    { name: "disputed", label: "Disputes", options: [["true", "Open"], ["false", "None"]] },
  ];
  return <div className="space-y-4 classification-page"><h1 className="text-xl font-bold">Review questions</h1><p>Read the complete question and available answer, then review every topic label with source evidence.</p>
    <div className="flex flex-wrap gap-3">{[["paper_id", "Paper"], ["source", "Source type"], ["taxonomy_version_id", "Taxonomy revision"]].map(([name, label]) => <label key={name}>{label} <select aria-label={label} className={control} value={params.get(name) ?? ""} onChange={e => filter(name, e.target.value)}><option value="">All</option>{[...new Set(items.map(value => name === "paper_id" ? value.paper_id : name === "source" ? value.question.source_family : String(value.taxonomy_version_id)))].filter(Boolean).map(value => <option key={value} value={value!}>{value}</option>)}</select></label>)}
      {filterOptions.map(({ name, label, options }) => <label key={name}>{label} <select aria-label={label} className={control} value={params.get(name) ?? ""} onChange={e => filter(name, e.target.value)}><option value="">All</option>{options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>)}
      <label><input type="checkbox" checked={blind} onChange={e => filter("blind", e.target.checked ? "true" : "")} /> Blind benchmark mode</label><label><input type="checkbox" checked={params.get("benchmark_only") === "true"} onChange={e => filter("benchmark_only", e.target.checked ? "true" : "")} /> Benchmark sample only</label>
    </div><div className="flex gap-3"><button className={control} disabled={Number(params.get("offset") ?? 0) === 0 || mutation.isPending} onClick={() => filter("offset", String(Math.max(0, Number(params.get("offset") ?? 0) - 100)))}>Previous queue page</button><button className={control} disabled={items.length < 100 || mutation.isPending} onClick={() => filter("offset", String(Number(params.get("offset") ?? 0) + 100))}>Next queue page</button></div><RequestError error={queue.error} retry={() => void queue.refetch()} /><RequestError error={mutation.error} retryLabel="Refresh current revision" retry={() => { setConfirmed(false); void queue.refetch(); }} />{message && <p role="status">{message}</p>}
    {queue.isPending ? <WorkspaceSkeleton label="Loading review queue…" /> : queue.isError ? null : !item ? <p>No root questions match these filters.</p> : <>
      <div className="flex gap-3 items-center"><button className={control} disabled={index === 0 || mutation.isPending} onClick={() => setSelected(items[index - 1].suggestion_revision_id)}>Previous question</button><span>{index + 1} / {items.length}</span><button className={control} disabled={index === items.length - 1 || mutation.isPending} onClick={() => setSelected(items[index + 1].suggestion_revision_id)}>Next question</button></div>
      <ReviewWorkspace tab={tab} changeTab={setTab} queue={<><h2 className="font-semibold mb-3">Review queue</h2>{items.map((value, row) => <button type="button" key={value.suggestion_revision_id} className="review-queue-row" aria-current={row === index} disabled={mutation.isPending} onClick={() => setSelected(value.suggestion_revision_id)}><strong>{value.question.display_label}</strong><span>{value.paper_id} · {value.attempt_id ?? value.question.source_collection_id ?? "Undated collection"}</span><span>{value.mappings.some(part => part.outcome === "needs_review") ? "Needs review" : "Labels proposed"} · {value.publication_ready ? "Ready" : "Blocked"}</span></button>)}</>} question={<section className={panel}><p className="text-sm">{item.paper_id} · {item.attempt_id ?? item.question.source_collection_id ?? "Undated collection"}</p><h2 className="font-semibold">{item.question.display_label}</h2><h3>Question and shared case context</h3><p className="whitespace-pre-wrap">{item.question.common_stem}</p><p className="whitespace-pre-wrap">{item.question.question_text}</p><QuestionParts parts={item.question.parts} selected={activePart} onSelect={selectPart} />{(item.question.choices ?? []).length > 0 && <section><h3>Choices and OR structure</h3>{(item.question.choices ?? []).map(choice => <p key={choice.label}>{choice.label} · {choice.role}{choice.or_group ? ` · OR ${choice.or_group}` : ""}{choice.marks != null ? ` · ${choice.marks} marks` : ""}</p>)}</section>}<details><summary>Technical details</summary><p>Suggestion {item.suggestion_revision_id} · extraction {item.extraction_revision_id} · taxonomy {item.taxonomy_version_id}</p></details></section>} answer={<section className={panel}><h2 className="font-semibold">Available complete answer · {item.question.answer_status}</h2>{item.question.answer_status === "partial" && <p>Partial answer: some parts have no reviewed answer.</p>}{item.question.answers.length ? <Answers parts={item.question.answers} /> : <p className="text-amber-200">No reviewed answer is available for this question.</p>}</section>} labels={<>      <section className={panel}><h2 className="font-semibold">Complete part-to-label mapping</h2>{blind && <p>Suggestions and model evidence remain hidden until your blind review is submitted.</p>}{mappings.map(part => <div key={part.part_id} id={`mapping-${part.part_id}`} className={`border-t border-slate-700 pt-3 space-y-2 ${activePart === part.part_id ? "border-l-4 border-indigo-400 pl-3" : ""}`}><button type="button" className={control} onClick={() => { setActivePart(part.part_id); setTab("Question"); document.getElementById(`part-${part.part_id}`)?.scrollIntoView({ block: "center" }); }}>Read this part</button><p className="font-mono text-xs">{part.part_id.split(":").slice(1).join(":") || item.question.display_label}</p>
        <select aria-label={`Outcome ${part.part_id}`} className={control} value={part.excluded ? "excluded" : part.outcome} onChange={e => { const value = e.target.value; update(part.part_id, { outcome: value === "excluded" ? "none_fits" : value as PartMapping["outcome"], excluded: value === "excluded", ...(value !== "matched" ? { primary_node_id: null, secondary_node_ids: [] } : {}) }); }}><option value="matched">Matched</option><option value="needs_review">Needs review</option><option value="none_fits">None fits</option><option value="excluded">Exclude from classification</option></select>
        <p>Primary: {part.primary_node_id ? <LabelPath id={part.primary_node_id} item={item} /> : "No primary label"}</p>{(part.secondary_node_ids ?? []).map(id => <p key={id}>Secondary: <LabelPath id={id} item={item} /> <button className={control} onClick={() => update(part.part_id, { secondary_node_ids: part.secondary_node_ids!.filter(value => value !== id) })}>Remove secondary</button></p>)}
        <div className="flex gap-2"><button className={control} disabled={mutation.isPending} onClick={() => setPicker({ part: part.part_id, secondary: false })}>Change primary</button><button className={control} disabled={!part.primary_node_id || mutation.isPending} onClick={() => setPicker({ part: part.part_id, secondary: true })}>Add secondary label</button></div>{!blind && <><MappingEvidence mapping={part} /><details><summary>Model evidence and alternatives</summary><p className="text-xs">Model confidence: {part.confidence ?? "unavailable"} · uncalibrated · bucket {part.bucket ?? "unavailable"}</p><pre className="text-xs whitespace-pre-wrap">{JSON.stringify(part.evidence, null, 2)}</pre></details></>}
      </div>)}{!blind && <details><summary>Method, alternatives and pinned evidence</summary><pre className="text-xs whitespace-pre-wrap break-all">{JSON.stringify(item.provenance, null, 2)}</pre>{(item.candidates as Candidate[]).map(candidate => <details key={candidate.node_id}><summary><LabelPath id={candidate.node_id} item={item} /></summary><p>Descriptor revision {candidate.descriptor_revision_id}</p><pre className="text-xs whitespace-pre-wrap">{JSON.stringify({ descriptor: candidate.descriptor, textbook_references: candidate.textbook_references }, null, 2)}</pre></details>)}</details>}</section>
      <section className={panel}><h2 className="font-semibold">Current publication {item.publication_revision_id ?? "none"}</h2><p>Topic labels verified by {item.verification_count ?? "an unknown number of"} students</p><p className="text-sm">Extraction-quality review is separate.</p>{!blind && item.published_mappings?.map(part => <p key={part.part_id}>{part.part_id.split(":").slice(1).join(":") || item.question.display_label}: {part.primary_node_id ? <LabelPath id={part.primary_node_id} item={item} /> : part.excluded ? "Excluded" : part.outcome}{part.secondary_node_ids?.map(id => <span key={id}> · <LabelPath id={id} item={item} /></span>)}</p>)}{item.dispute_status && <p className="text-amber-200">Dispute {item.dispute_status}; the previous publication remains visible.</p>}
        {!blind && item.published_question && <details><summary>Question and answer for the current published revision</summary><p className="whitespace-pre-wrap">{item.published_question.common_stem}</p><p className="whitespace-pre-wrap">{item.published_question.question_text}</p><QuestionParts parts={item.published_question.parts} /><p>Published answer status: {item.published_question.answer_status}</p><Answers parts={item.published_question.answers} /></details>}
        {item.publication_revision_id && !blind && <button className={control} disabled={mutation.isPending} onClick={() => submit(item.verified_by_me ? "withdraw" : "verify")}>{item.verified_by_me ? "Withdraw my topic verification" : "Verify the current published mapping"}</button>}<button className={control} disabled={blind} onClick={() => setShowHistory(value => !value)}>Revision history and correction differences</button>
        {showHistory && <><RequestError error={history.error} retry={() => void history.refetch()} />{history.data?.map(revision => <details key={revision.id}><summary>Revision {revision.id} · {revision.status} · verified by {revision.verification_count} students</summary><p>{revision.note}</p><pre className="text-xs whitespace-pre-wrap">{JSON.stringify(revision.mappings, null, 2)}</pre></details>)}</>}
        {!blind && item.publication_revision_id && <div><h3 className="font-semibold">Changes before confirmation</h3>{mappings.map(part => <div key={part.part_id} className="border-l border-slate-600 pl-3"><p>{part.part_id.split(":").slice(1).join(":") || item.question.display_label}</p><p>Published: <MappingSummary mapping={item.published_mappings?.find(value => value.part_id === part.part_id)} item={item} /></p><p>Proposed: <MappingSummary mapping={part} item={item} /></p></div>)}</div>}
      </section></>} evidence={<>      <section className={panel}><h2 className="font-semibold">Classification readiness</h2><p>{item.experimental ? "Experimental suggestion" : "Reviewed input suggestion"}{item.stale && " · Stale inputs"}</p>{item.readiness_blockers.map(block => <p key={block.code} className="text-sm text-amber-200">{block.message}</p>)}{item.publication_ready && <p className="text-emerald-300">Eligible for authenticated student review</p>}</section>
<button className={control} onClick={() => setEvidenceOpen(value => !value)}>Extraction and source evidence</button>{evidenceOpen && <><RequestError error={extraction.error} retry={() => void extraction.refetch()} />{extraction.data && <ExtractionEvidence revision={extraction.data} admin={admin} onCorrected={() => { void queue.refetch(); }} />}</>}
</>} footer={<section className={panel}><label className="block">Review evidence or correction reason<textarea aria-label="Review evidence or correction reason" className={`${control} w-full block mt-2`} value={note} maxLength={10000} onChange={e => setNote(e.target.value)} /></label><label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> I reviewed the complete question, available answer and every part label</label>
        <div className="flex gap-3 flex-wrap"><button className={control} disabled={!confirmed || !note.trim() || (unresolved && !blind) || (!item.publication_ready && !blind) || mutation.isPending} onClick={() => submit("review")}>{blind ? "Save blind review" : "Publish reviewed labels"}</button>{!blind && item.publication_revision_id && <button className={control} disabled={!note.trim() || mutation.isPending} onClick={() => submit("dispute")}>Submit correction or dispute</button>}{!blind && admin && item.dispute_status && <><button className={control} disabled={!confirmed || !note.trim() || mutation.isPending} onClick={() => submit("dismiss")}>Resolve dispute: retain publication</button><button className={control} disabled={!confirmed || !note.trim() || unresolved || mutation.isPending} onClick={() => submit("replace")}>Resolve dispute: publish reviewed replacement</button></>}</div>
      </section>} />
      <NodePickerModal candidates={(item.candidates as Candidate[]).map(value => ({ id: value.node_id, name: value.path[value.path.length - 1]?.name ?? value.node_id, paperCode: item.paper_id ?? "", chapterName: value.path.map(node => node.name).join(" → "), topicName: "" }))} isOpen={!!picker && !mutation.isPending} onClose={() => setPicker(null)} onSelect={id => { if (!picker) return; const part = mappings.find(value => value.part_id === picker.part)!; update(picker.part, picker.secondary ? { secondary_node_ids: [...new Set([...(part.secondary_node_ids ?? []), id])].filter(value => value !== part.primary_node_id) } : { primary_node_id: id, secondary_node_ids: part.secondary_node_ids?.filter(value => value !== id), outcome: "matched", excluded: false }); }} />
    </>}
    <dialog ref={conflictDialog} className="review-dialog" aria-labelledby="conflict-title"><h2 id="conflict-title">This review has changed</h2><p role="alert">{mutation.error?.message}</p><p>Your proposed labels and evidence are retained. Refresh the current publication, compare Current / Proposed, and confirm the complete review again.</p><button type="button" onClick={() => { conflictDialog.current?.close(); setConfirmed(false); void queue.refetch(); }}>Refresh current revision for comparison</button><button type="button" onClick={() => conflictDialog.current?.close()}>Keep reviewing</button></dialog>
  </div>;
}
