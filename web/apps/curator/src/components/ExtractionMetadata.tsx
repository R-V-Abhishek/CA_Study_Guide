import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { extractionApi, type ExtractionDocument } from "@caf/api-client/src/extraction";
import { RequestError } from "./RequestError";

const control = "rounded border border-slate-600 bg-slate-900 p-2 text-sm";
const papers = ["Financial Reporting", "Advanced Financial Management", "Advanced Auditing, Assurance and Professional Ethics", "Direct Tax Laws and International Taxation", "Indirect Tax Laws", "Integrated Business Solutions"];
const roles = ["question_paper", "suggested_answer", "rtp", "mtp_question", "mtp_answer", "model_question", "model_answer", "case_scenarios", "ibs_case_study"];
export function ExtractionMetadata({ document, refresh }: { document: ExtractionDocument; refresh: () => Promise<void> }) {
  const [paper, setPaper] = useState(document.paper_id ?? "");
  const [attempt, setAttempt] = useState(document.attempt_id ?? "");
  const [collection, setCollection] = useState(document.collection_id ?? "");
  const [role, setRole] = useState(document.doc_type_id ?? "question_paper");
  const [ranges, setRanges] = useState(document.paper_page_ranges ?? []);
  const save = useMutation({ mutationFn: () => extractionApi.confirmMetadata(document.id, {
    course_level: "final", scheme_id: document.scheme_id ?? "s2023", paper_id: paper || null,
    attempt_id: attempt || null, collection_id: collection || null, doc_type_id: role, paper_page_ranges: ranges,
  }), onSuccess: refresh });
  return <section className="rounded-xl border border-slate-700 bg-slate-800/50 p-4 space-y-3"><h2 className="font-semibold">Confirm source identity</h2>
    <p className="text-sm text-slate-300">Compare the official source pages before confirming its paper, role and attempt or collection.</p>
    {(document.metadata_evidence?.conflicts?.length ?? 0)>0 && <div className="text-amber-200 text-sm"><p>Navigation and document contents conflict. Confirm the identity shown in the original source.</p><ul>{document.metadata_evidence?.conflicts?.map((conflict,index) => <li key={index}>{String(conflict.field)}: {conflict.reason ? String(conflict.reason) : `navigation ${String(conflict.navigation)}; document ${String(conflict.content)}`}</li>)}</ul></div>}
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); save.mutate(); }}>
      <div className="flex gap-3 flex-wrap"><label>Source paper <select aria-label="Source paper" className={control} value={paper} onChange={event => setPaper(event.target.value)}><option value="">Combined papers or unresolved</option>{papers.map((name, index) => <option key={name} value={`s2023.P${index+1}`}>P{index+1} · {name}</option>)}</select></label>
        <label>Document role <select className={control} value={role} onChange={event => setRole(event.target.value)}>{roles.map(value => <option key={value} value={value}>{value.replace(/_/g, " ")}</option>)}</select></label>
        <label>Source attempt <input className={control} value={attempt} onChange={event => setAttempt(event.target.value)} placeholder="YYYY-MM; blank for undated collections" pattern="[0-9]{4}-[0-9]{2}" /></label>
        <label>Source collection <input className={control} value={collection} onChange={event => setCollection(event.target.value)} /></label></div>
      <fieldset className="space-y-2"><legend className="font-semibold">Paper-specific page ranges</legend>{ranges.map((range,index) => <div className="flex gap-2 flex-wrap" key={index}>
        <label>Range {index+1} paper <select className={control} value={range.paper_id} onChange={event => setRanges(ranges.map((item,i) => i===index ? {...item,paper_id:event.target.value} : item))}>{papers.map((name,i) => <option key={name} value={`s2023.P${i+1}`}>P{i+1} · {name}</option>)}</select></label>
        <label>Range {index+1} first page <input className={`${control} w-24`} type="number" min={1} max={document.page_count ?? undefined} value={range.page_start} onChange={event => setRanges(ranges.map((item,i) => i===index ? {...item,page_start:Number(event.target.value)} : item))} required /></label>
        <label>Range {index+1} last page <input className={`${control} w-24`} type="number" min={range.page_start} max={document.page_count ?? undefined} value={range.page_end} onChange={event => setRanges(ranges.map((item,i) => i===index ? {...item,page_end:Number(event.target.value)} : item))} required /></label>
        <button className={control} type="button" onClick={() => setRanges(ranges.filter((_,i) => i!==index))}>Remove range {index+1}</button></div>)}
        <button className={control} type="button" onClick={() => setRanges([...ranges,{paper_id:paper || "s2023.P1",page_start:1,page_end:1}])}>Add paper range</button></fieldset>
      <button className={control} disabled={save.isPending}>{save.isPending ? "Confirming source…" : "Confirm source metadata"}</button>
    </form><RequestError error={save.error} />{save.isSuccess && <p role="status">Source metadata confirmed. Changed identities require a new extraction candidate.</p>}
  </section>;
}
