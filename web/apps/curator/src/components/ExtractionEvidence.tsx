import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accountKey } from "@caf/api-client";
import { extractionApi, type ExtractionRevision, type ExtractionQuestionPart, type ExtractionCorrection } from "@caf/api-client/src/extraction";
import { RequestError } from "./RequestError";
import { Pagination } from "../pages/Extraction";

const control = "rounded border border-slate-600 bg-slate-900 p-2 text-sm";
const panel = "rounded-xl border border-slate-700 bg-slate-800/50 p-4 space-y-3";

function paths(parts: ExtractionQuestionPart[]): string[] {
  return parts.flatMap(part => [...(part.label_path ? [part.label_path] : []), ...paths(part.parts)]);
}

function AssetPreview({ id }: { id: number }) {
  const [url, setUrl] = useState("");
  const asset = useQuery({ queryKey: ["extraction-asset-image", accountKey(), id], queryFn: () => extractionApi.asset(id), retry: false });
  useEffect(() => {
    setUrl("");
    if (!asset.data) return;
    const next = URL.createObjectURL(asset.data); setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [asset.data]);
  return <><RequestError error={asset.error} retry={() => void asset.refetch()} />{asset.isFetching && <p role="status">Loading source crop…</p>}{url && <img src={url} alt={`Original source asset ${id}`} className="max-w-full bg-white" />}</>;
}

export function ExtractionEvidence({ revision, admin, onCorrected }: { revision: ExtractionRevision; admin: boolean; onCorrected: (id: number) => void }) {
  const cache = useQueryClient();
  const [pairPage, setPairPage] = useState(1);
  const [reconciliationPage, setReconciliationPage] = useState(1);
  const [blockPage, setBlockPage] = useState(1);
  const [assetPage, setAssetPage] = useState(1);
  const [reviewPage, setReviewPage] = useState(1);
  const [assetId, setAssetId] = useState<number | null>(null);
  const [answerDocument, setAnswerDocument] = useState("");
  const [pairEvidence, setPairEvidence] = useState("");
  const labels = revision.questions.flatMap(question => [question.label_path, ...paths(question.parts)]);
  const [label, setLabel] = useState(labels[0] ?? "");
  const [field, setField] = useState("question_text");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [startPage, setStartPage] = useState("");
  const [endPage, setEndPage] = useState("");
  const [startBlock, setStartBlock] = useState("");
  const [endBlock, setEndBlock] = useState("");
  const answerCandidates = revision.questions.flatMap(question => question.pairing_candidates ?? []).find(group => group.label_path === label)?.candidates ?? [];
  const pairs = useQuery({ queryKey: ["extraction-pairs", accountKey(), revision.document_id, pairPage], queryFn: () => extractionApi.pairs(revision.document_id, pairPage), retry: false });
  const reconciliation = useQuery({ queryKey: ["extraction-reconciliation", accountKey(), revision.id, reconciliationPage], queryFn: () => extractionApi.reconciliation(revision.id, reconciliationPage), retry: false });
  const blocks = useQuery({ queryKey: ["extraction-blocks", accountKey(), revision.id, blockPage], queryFn: () => extractionApi.blocks(revision.id, blockPage), retry: false });
  const assets = useQuery({ queryKey: ["extraction-assets", accountKey(), revision.id, assetPage], queryFn: () => extractionApi.assets(revision.id, assetPage), retry: false });
  const reviews = useQuery({ queryKey: ["extraction-reviews", accountKey(), revision.id, reviewPage], queryFn: () => extractionApi.reviews(revision.id, reviewPage), retry: false });
  const refreshPairs = () => cache.invalidateQueries({ queryKey: ["extraction-pairs", accountKey(), revision.document_id] });
  const pair = useMutation({ mutationFn: () => extractionApi.pair(revision.document_id, Number(answerDocument), pairEvidence), onSuccess: async () => { setPairEvidence(""); await refreshPairs(); } });
  const reject = useMutation({ mutationFn: extractionApi.rejectPair, onSuccess: refreshPairs });
  const correction = useMutation({ mutationFn: () => {
    const body: ExtractionCorrection = { label_path: label, reason };
    if (field === "question_text") body.question_text = value;
    if (field === "answer_text") body.answer_text = value;
    if (field === "answer_candidate") body.answer_candidate_label = value;
    if (field === "marks") body.marks = Number(value);
    if (field === "source_span") {
      body.page_start = Number(startPage); body.page_end = Number(endPage);
      body.block_start = startBlock; body.block_end = endBlock;
    }
    return extractionApi.correct(revision.id, body);
  }, onSuccess: result => onCorrected(result.id) });
  return <div className="space-y-4">
    <section className={panel}><h2 className="font-semibold">Recorded extraction reviews</h2><RequestError error={reviews.error} retry={() => void reviews.refetch()} />{reviews.data?.items.length === 0 && <p>No human extraction review has been recorded for this revision.</p>}{reviews.data?.items.map(item => <div key={item.id}><p>{item.dimension} · {item.status} · reviewer {item.actor_id}</p><p className="text-sm whitespace-pre-wrap">{item.note}</p><p className="text-xs break-all">Reviewed content digest: {item.content_digest}</p></div>)}{reviews.data && <Pagination page={reviewPage} total={reviews.data.total} size={reviews.data.page_size} name="reviews" change={setReviewPage} />}</section>
    <section className={panel}><h2 className="font-semibold">Document pairing evidence</h2><RequestError error={pairs.error} retry={() => void pairs.refetch()} />
      {pairs.data?.items.length === 0 && <p>No confirmed answer-document pair is recorded.</p>}
      {pairs.data?.items.map(item => <div key={item.id}><p>Question document {item.question_document_id} → answer document {item.answer_document_id} · {item.status}</p><pre className="whitespace-pre-wrap text-xs">{JSON.stringify(item.evidence, null, 2)}</pre>{admin && item.status === "confirmed" && <button className={control} disabled={reject.isPending} onClick={() => reject.mutate(item.id)}>Reject pair {item.id}</button>}</div>)}
      {pairs.data && <Pagination page={pairPage} total={pairs.data.total} size={pairs.data.page_size} name="pairs" change={setPairPage} />}
      {admin && <form className="space-y-3" onSubmit={event => { event.preventDefault(); pair.mutate(); }}><p className="text-sm text-slate-300">Confirm a pair from its official identity and contents. The next extraction uses the confirmed answer source.</p><label className="block">Answer document ID <input className={control} type="number" min={1} required value={answerDocument} onChange={event => setAnswerDocument(event.target.value)} /></label><label className="block">Pairing evidence <textarea className={`${control} block w-full`} required maxLength={10000} value={pairEvidence} onChange={event => setPairEvidence(event.target.value)} /></label><button className={control} disabled={pair.isPending}>Confirm document pair</button><RequestError error={pair.error ?? reject.error} />{pair.isSuccess && <p role="status">Document pair confirmed. Existing revisions retain their recorded source evidence.</p>}</form>}
    </section>
    <section className={panel}><h2 className="font-semibold">Revision reconciliation</h2><RequestError error={reconciliation.error} retry={() => void reconciliation.refetch()} />{reconciliation.data?.items.length === 0 && <p>No predecessor matches are recorded.</p>}{reconciliation.data?.items.map(item => <div key={item.id}><p>{item.relation} · old unit {item.old_unit_id ?? "none"} → {item.new_label ?? "unmatched"}</p><pre className="whitespace-pre-wrap text-xs">{JSON.stringify(item.evidence, null, 2)}</pre></div>)}{reconciliation.data && <Pagination page={reconciliationPage} total={reconciliation.data.total} size={reconciliation.data.page_size} name="matches" change={setReconciliationPage} />}</section>
    <section className={panel}><h2 className="font-semibold">Ordered source blocks</h2><RequestError error={blocks.error} retry={() => void blocks.refetch()} />{blocks.data?.items.map(block => <details key={block.id}><summary>{block.block_key} · page {block.page} · {block.origin}</summary><p className="whitespace-pre-wrap text-sm">{block.raw_text}</p><p className="text-xs">Bounding box: {block.bbox.join(", ")}</p></details>)}{blocks.data && <Pagination page={blockPage} total={blocks.data.total} size={blocks.data.page_size} name="blocks" change={setBlockPage} />}</section>
    <section className={panel}><h2 className="font-semibold">Source crops and uncertain layouts</h2><RequestError error={assets.error} retry={() => void assets.refetch()} />{assets.data?.items.length === 0 && <p>No source crops are recorded for this revision.</p>}{assets.data?.items.map(asset => <div key={asset.id}><button className={control} onClick={() => setAssetId(asset.id)}>View {asset.kind} on page {asset.page}</button><p className="text-sm text-amber-200">{asset.concerns.join(" · ")}</p></div>)}{assets.data && <Pagination page={assetPage} total={assets.data.total} size={assets.data.page_size} name="assets" change={setAssetPage} />}{assetId !== null && <AssetPreview id={assetId} />}</section>
    {admin && labels.length > 0 && <section className={panel}><h2 className="font-semibold">Audited extraction correction</h2><p className="text-sm text-slate-300">A correction creates a new candidate revision with its reason and source lineage. Review the candidate before promotion.</p><form className="space-y-3" onSubmit={event => { event.preventDefault(); correction.mutate(); }}>
      <div className="flex flex-wrap gap-3"><label>Scoped question or part <select className={control} value={label} onChange={event => { setLabel(event.target.value); setValue(""); }}>{labels.map(path => <option key={path} value={path}>{path}</option>)}</select></label><label>Correction field <select className={control} value={field} onChange={event => { setField(event.target.value); setValue(""); }}><option value="question_text">Question text</option><option value="answer_text">Available answer text</option><option value="answer_candidate">Resolve answer source candidate</option><option value="marks">Marks</option><option value="source_span">Source page and block span</option></select></label></div>
      {field === "answer_candidate" && <label className="block">Selected answer source <select aria-label="Selected answer source" className={control} required value={value} onChange={event => setValue(event.target.value)}><option value="">Choose a recorded candidate</option>{answerCandidates.map(candidate => <option key={candidate.label_path} value={candidate.label_path}>{candidate.label_path} · document {candidate.answer_doc_id} · pages {candidate.page_start}–{candidate.page_end}</option>)}</select></label>}
      {field === "source_span" ? <div className="flex flex-wrap gap-3"><label>First source page <input className={`${control} w-24`} type="number" min={1} required value={startPage} onChange={event => setStartPage(event.target.value)} /></label><label>Last source page <input className={`${control} w-24`} type="number" min={Number(startPage) || 1} required value={endPage} onChange={event => setEndPage(event.target.value)} /></label><label>First block key <input className={control} required value={startBlock} onChange={event => setStartBlock(event.target.value)} /></label><label>Last block key <input className={control} required value={endBlock} onChange={event => setEndBlock(event.target.value)} /></label></div> : field !== "answer_candidate" && <label className="block">Corrected value {field === "marks" ? <input className={control} type="number" min={0} max={100} required value={value} onChange={event => setValue(event.target.value)} /> : <textarea className={`${control} block w-full`} required value={value} onChange={event => setValue(event.target.value)} />}</label>}
      <label className="block">Correction reason <textarea className={`${control} block w-full`} required maxLength={10000} value={reason} onChange={event => setReason(event.target.value)} /></label><button className={control} disabled={correction.isPending}>{correction.isPending ? "Creating corrected candidate…" : "Create corrected candidate revision"}</button><RequestError error={correction.error} />
    </form></section>}
  </div>;
}
