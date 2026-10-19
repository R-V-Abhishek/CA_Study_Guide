import { useRef, useState, useSyncExternalStore } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accountKey, authState, subscribeAuth } from "@caf/api-client";
import { extractionApi, type ExtractedQuestion, type ExtractionQuestionPart, type ExtractionAnswerPart, type ExtractionSpan } from "@caf/api-client/src/extraction";
import { RequestError } from "../components/RequestError";
import { ExtractionEvidence } from "../components/ExtractionEvidence";
import { WorkspaceSkeleton } from "../components/WorkspaceSkeleton";

import { SourcePage } from "../components/SourcePage";
import { ExtractionMetadata } from "../components/ExtractionMetadata";
import "../components/review-workspace.css";

const dimensions = ["questions", "answers", "pairing", "ordering", "marks_choices", "readability", "human_review"];
const control = "rounded border border-slate-600 bg-slate-900 p-2 text-sm";
const panel = "rounded-xl border border-slate-700 bg-slate-800/50 p-4 space-y-3";

export function Pagination({ page, total, size, change, name }: { page: number; total: number; size: number; change: (page: number) => void; name: string }) {
  return <nav aria-label={`${name} pagination`} className="flex items-center gap-3 text-sm"><button className={control} disabled={page <= 1} onClick={() => change(page - 1)}>Previous {name}</button><span>Page {page} · {total} {name}</span><button className={control} disabled={page * size >= total} onClick={() => change(page + 1)}>Next {name}</button></nav>;
}

function SourceSpans({ spans, open }: { spans: ExtractionSpan[]; open: (span: ExtractionSpan) => void }) {
  return <div className="flex gap-2 flex-wrap text-xs text-indigo-300">{spans.map((span, index) => <button className="underline" key={index} onClick={() => open(span)}>Source pages {span.page_start}–{span.page_end}</button>)}</div>;
}

function QuestionParts({ parts, open }: { parts: ExtractionQuestionPart[]; open: (span: ExtractionSpan) => void }) {
  return <ol className="space-y-3 ml-3 border-l border-slate-600 pl-3">{parts.map(part => <li key={part.id}><p className="font-medium">{part.label}{part.marks != null ? ` · ${part.marks} marks` : ""}</p><p className="whitespace-pre-wrap">{part.question_text}</p><SourceSpans spans={part.source_spans} open={open} />{part.parts.length > 0 && <QuestionParts parts={part.parts} open={open} />}</li>)}</ol>;
}

function AnswerParts({ parts, open }: { parts: ExtractionAnswerPart[]; open: (span: ExtractionSpan) => void }) {
  return <ol className="space-y-3 ml-3 border-l border-slate-600 pl-3">{parts.map(part => <li key={part.id}><p className="text-xs text-slate-400">Answer for {part.question_part_id ?? "whole question"}</p><p className="whitespace-pre-wrap">{part.answer_text}</p><SourceSpans spans={part.source_spans} open={open} />{part.parts.length > 0 && <AnswerParts parts={part.parts} open={open} />}</li>)}</ol>;
}

function Question({ question, open, openDocument }: { question: ExtractedQuestion; open: (span: ExtractionSpan) => void; openDocument: (document: number, page: number) => void }) {
  return <article className={panel} aria-label={question.display_label}><h3 className="font-semibold">{question.display_label} · {question.paper_id} · {question.source_attempt_id ?? "Undated collection"}</h3><details><summary>Technical details</summary><p className="text-xs text-slate-400 break-all">Identity: {question.question_id} · Content revision: {question.content_revision}</p></details>
    <div className="extraction-question-content"><p className="text-xs text-slate-300">{question.course_level} · Scheme {question.scheme_id} · {question.source_family} · Collection {question.source_collection_id ?? "Unspecified"}</p><p className="text-xs text-amber-200">Question: {question.question_status} · Pairing: {question.pairing_status} · Readability: {question.readability_status} · Review: {question.review_status}</p>
    {question.common_stem && <p className="whitespace-pre-wrap">{question.common_stem}</p>}{question.question_text && question.question_text !== question.common_stem && <p className="whitespace-pre-wrap">{question.question_text}</p>}
    <SourceSpans spans={question.source_spans} open={open} /><QuestionParts parts={question.parts} open={open} />
    {question.choices.length > 0 && <div><h4 className="font-semibold">Choices and marks</h4><ul className="text-sm space-y-1">{question.choices.map(choice => <li key={choice.label}>{choice.label}: {choice.role}{choice.or_group ? ` · OR group ${choice.or_group}` : ""}{choice.marks !== null ? ` · ${choice.marks} marks` : ""}</li>)}</ul></div>}
    {question.mcq.length > 0 && <div><h4 className="font-semibold">MCQ options and keys</h4>{question.mcq.map(mcq => <div key={mcq.part_id}><p className="text-sm">Part {mcq.part_id}</p><ul className="whitespace-pre-wrap text-sm">{mcq.options.map((option, index) => <li key={index}>{option}</li>)}</ul><p>Answer key: {mcq.key ?? "Not available"}</p></div>)}</div>}
    </div><div className="extraction-answer-content"><h4 className="font-semibold">Available answers · {question.answer_status}</h4>{question.answers.length ? <AnswerParts parts={question.answers} open={open} /> : <p className="text-amber-200">No answer text is available for this question.</p>}
    </div>{(question.pairing_candidates ?? []).filter(group => group.status === "ambiguous").map(group => <section className="space-y-3 border-t border-amber-700 pt-3" key={group.part_id} aria-label={`Unresolved answer pairing ${group.label_path}`}><h4 className="font-semibold text-amber-200">Unresolved answer pairing · {group.label_path}</h4><p className="text-sm text-amber-200">{group.candidates.length} candidate answers require source review.</p>{group.candidates.map((candidate, index) => <div className="space-y-2 rounded border border-slate-600 p-3" key={`${candidate.label_path}:${index}`}><h5 className="text-sm font-semibold">Candidate {candidate.label_path} · answer document {candidate.answer_doc_id ?? "unresolved"}</h5>{candidate.answer_text ? <p className="whitespace-pre-wrap">{candidate.answer_text}</p> : <p className="text-sm text-slate-400">No narrative answer text is recorded for this candidate.</p>}{candidate.mcq_correct_option && <p>MCQ key: {candidate.mcq_correct_option}</p>}<p className="text-xs text-slate-400">Blocks: {candidate.block_start ?? "unresolved"} → {candidate.block_end ?? "unresolved"}</p>{candidate.answer_doc_id !== null && candidate.page_start !== null && <button type="button" className="text-xs text-indigo-300 underline" onClick={() => openDocument(candidate.answer_doc_id!, candidate.page_start!)}>Candidate source pages {candidate.page_start}–{candidate.page_end ?? candidate.page_start} · document {candidate.answer_doc_id}</button>}</div>)}</section>)}
  </article>;
}


export function Extraction() {
  const [params, setParams] = useSearchParams();
  const identity = useSyncExternalStore(subscribeAuth, authState);
  const admin = identity.identity?.capabilities.includes("admin") ?? false;
  const cache = useQueryClient();
  const [tab, setTab] = useState("Question assembly");
  const [readingPane, setReadingPane] = useState("Question");
  const [promotionOpen, setPromotionOpen] = useState(false);
  const promotionDialog = useRef<HTMLDialogElement>(null);
  const [promotionConfirmed, setPromotionConfirmed] = useState(false);
  const [documentPage, setDocumentPage] = useState(1);
  const [revisionPage, setRevisionPage] = useState(1);
  const [selectedDocument, setSelectedDocument] = useState<number | null>(params.get("document_id") ? Number(params.get("document_id")) : null);
  const [selectedRevision, setSelectedRevision] = useState<number | null>(params.get("revision") ? Number(params.get("revision")) : null);
  const [comparison, setComparison] = useState<number | null>(null);
  const [questionPage, setQuestionPage] = useState(1);
  const [sourceDocument, setSourceDocument] = useState<number | null>(params.get("document_id") ? Number(params.get("document_id")) : null);
  const [sourcePage, setSourcePage] = useState(1);
  const [sourceError, setSourceError] = useState<Error | null>(null);
  const [dimension, setDimension] = useState(dimensions[0]);
  const [reviewStatus, setReviewStatus] = useState("passed");
  const [note, setNote] = useState("");
  const docs = useQuery({ queryKey: ["extraction-documents", accountKey(), documentPage], queryFn: () => extractionApi.documents(documentPage), retry: false });
  const document = docs.data?.items.find(item => item.id === selectedDocument);
  const revisions = useQuery({ queryKey: ["extraction-revisions", accountKey(), selectedDocument, revisionPage], queryFn: () => extractionApi.revisions(selectedDocument!, revisionPage), enabled: selectedDocument !== null, retry: false });
  const revisionId = selectedRevision ?? revisions.data?.items[0]?.id;
  const revision = useQuery({ queryKey: ["extraction-revision", accountKey(), revisionId], queryFn: () => extractionApi.revision(revisionId!), enabled: revisionId !== undefined, retry: false });
  const questions = useQuery({ queryKey: ["extraction-questions", accountKey(), revisionId, questionPage], queryFn: () => extractionApi.questions(revisionId!, questionPage), enabled: revisionId !== undefined, retry: false });
  const previous = useQuery({ queryKey: ["extraction-revision", accountKey(), comparison], queryFn: () => extractionApi.revision(comparison!), enabled: comparison !== null, retry: false });
  const refresh = async () => { await cache.invalidateQueries({ queryKey: ["extraction-revision", accountKey()] }); await cache.invalidateQueries({ queryKey: ["extraction-revisions", accountKey()] }); await cache.invalidateQueries({ queryKey: ["extraction-documents", accountKey()] }); await cache.invalidateQueries({ queryKey: ["extraction-reviews", accountKey()] }); await cache.invalidateQueries({ queryKey: ["extraction-questions", accountKey()] }); };
  const review = useMutation({ mutationFn: () => extractionApi.review(revisionId!, dimension, reviewStatus, note), onSuccess: async () => { setNote(""); await refresh(); } });
  const promote = useMutation({ mutationFn: () => extractionApi.promote(revisionId!, document!.current_revision_id), onSuccess: refresh });
  const open = (span: ExtractionSpan) => {
    setReadingPane("Source");
    const sources = [...(revision.data?.source_documents ?? []), ...(previous.data?.source_documents ?? [])];
    const source = sources.find(item => item.sha256 === span.document_sha256);
    if (!source) { setSourceError(new Error("The source span has no registered document mapping. Record a source-fidelity concern.")); return; }
    setSourceError(null); setSourceDocument(source.id); setSourcePage(span.page_start);
  };
  const openDocument = (id: number, page: number) => {
    const source = [...(revision.data?.source_documents ?? []), ...(previous.data?.source_documents ?? [])].find(item => item.id === id);
    if (!source || page < 1 || (source.page_count !== null && page > source.page_count)) {
      setSourceError(new Error("The candidate source document or page is unresolved. Record a pairing concern.")); return;
    }
    setSourceError(null); setSourceDocument(id); setSourcePage(page);
  };
  const selectDocument = (id: number) => { setParams({ document_id: String(id) }); setTab("Question assembly"); setPromotionConfirmed(false); setSelectedDocument(id); setSelectedRevision(null); setRevisionPage(1); setComparison(null); setQuestionPage(1); setSourceDocument(id); setSourcePage(1); setSourceError(null); review.reset(); promote.reset(); };
  return <div className="space-y-5"><h1 className="text-xl font-bold">Extraction</h1><p className="text-sm text-slate-300">Compare complete questions and available answers with the original pages. Extraction quality reviews are recorded separately from topic classification.</p>
    <RequestError error={docs.error} retry={() => void docs.refetch()} />{docs.isPending && <WorkspaceSkeleton label="Loading source documents…" />}
    {docs.data && <section className={panel}><h2 className="font-semibold">Source documents</h2>{docs.data.items.length === 0 ? <p>No acquired source documents are available.</p> : <div className="flex flex-wrap gap-2">{docs.data.items.map(item => <button className={`${control} ${selectedDocument === item.id ? "border-indigo-400" : ""}`} key={item.id} onClick={() => selectDocument(item.id)}>{item.title ?? `Document ${item.id}`} · {item.paper_id ?? "Paper unresolved"} · {item.attempt_id ?? item.collection_id ?? "Undated"} · {item.doc_type_id ?? "Role unresolved"} · {item.catalog_status}</button>)}</div>}<Pagination page={documentPage} total={docs.data.total} size={docs.data.page_size} name="documents" change={page => { setDocumentPage(page); setSelectedDocument(null); setSelectedRevision(null); setComparison(null); setSourceDocument(null); }} /></section>}
    {selectedDocument !== null && <><RequestError error={revisions.error} retry={() => void revisions.refetch()} />{revisions.isPending && <p role="status">Loading extraction revisions…</p>}{revisions.data?.items.length === 0 && <p>No extraction revision has been generated for this document.</p>}
      {document && admin && <ExtractionMetadata key={document.id} document={document} refresh={refresh} />}
      {document && !revision.data && sourceDocument!==null && <SourcePage document={sourceDocument} page={sourcePage} pageCount={document.page_count} change={setSourcePage} />}
      {revisions.data && revisions.data.items.length > 0 && <section className={panel}><div className="flex gap-4 flex-wrap"><label>Extraction revision <select className={control} value={revisionId ?? ""} onChange={event => { setSelectedRevision(Number(event.target.value)); setParams({ document_id: String(selectedDocument), revision: event.target.value }); setQuestionPage(1); review.reset(); promote.reset(); }}>{revisions.data.items.map(item => <option key={item.id} value={item.id}>Revision {item.id} · {item.status}</option>)}</select></label><label>Compare revision <select className={control} value={comparison ?? ""} onChange={event => setComparison(event.target.value ? Number(event.target.value) : null)}><option value="">No comparison</option>{revisions.data.items.filter(item => item.id !== revisionId).map(item => <option key={item.id} value={item.id}>Revision {item.id} · {item.status}</option>)}</select></label></div><Pagination page={revisionPage} total={revisions.data.total} size={revisions.data.page_size} name="revisions" change={page => { setRevisionPage(page); setSelectedRevision(null); setComparison(null); setQuestionPage(1); }} /></section>}
      <RequestError error={revision.error} retry={() => void revision.refetch()} />
      {revision.data && <><p>Document: {document?.title ?? "Selected source"} · Candidate revision {revisionId} · Current revision {document?.current_revision_id ?? "None"}</p><div role="tablist" aria-label="Extraction workspace" className="flex flex-wrap gap-2">{["Question assembly", "Answer pairing", "Quality checks", "Revision differences"].map(name => <button type="button" className={control} key={name} role="tab" aria-selected={tab === name} onClick={() => setTab(name)}>{name}</button>)}</div><section hidden={tab !== "Quality checks"} className={panel}><h2 className="font-semibold">Quality evidence · {revision.data.status}</h2><details><summary>Technical details</summary><p className="text-xs break-all">Content digest: {revision.data.content_digest}</p></details><dl className="grid grid-cols-2 gap-2 text-sm">{["metadata", ...dimensions].map(key => <div key={key}><dt className="capitalize text-slate-400">{key.replace(/_/g, " ")}</dt><dd>{revision.data.quality[key as keyof typeof revision.data.quality]?.toString() ?? "Unrecorded"}</dd></div>)}</dl>{revision.data.quality.issues.length > 0 && <div><h3 className="font-semibold">Extraction issues</h3><ul className="space-y-2 text-sm text-amber-200">{revision.data.quality.issues.map((issue, index) => <li key={index}>{issue.message} <span className="text-xs">({issue.severity} · {issue.code})</span></li>)}</ul></div>}
        <form onSubmit={event => { event.preventDefault(); review.mutate(); }} className="space-y-3"><div className="flex gap-3 flex-wrap"><label>Quality dimension <select className={control} value={dimension} onChange={event => setDimension(event.target.value)}>{[...dimensions, ...(admin ? ["metadata"] : [])].map(value => <option key={value} value={value}>{value.replace(/_/g, " ")}</option>)}</select></label><label>Review result <select className={control} value={reviewStatus} onChange={event => setReviewStatus(event.target.value)}><option value="passed">Passed</option><option value="pending">Pending</option><option value="concern">Concern</option><option value="not_applicable">Not applicable</option></select></label></div><label className="block">Review note <textarea className={`${control} block w-full`} value={note} onChange={event => setNote(event.target.value)} required maxLength={10000} /></label><button className={control} disabled={review.isPending}>{review.isPending ? "Recording review…" : "Record extraction quality review"}</button></form><RequestError error={review.error} />{review.isSuccess && <p role="status">Extraction quality review recorded for this revision.</p>}
        {admin && document && <>{revision.data.status === "candidate" && <button className={control} disabled={promote.isPending} onClick={() => { setPromotionConfirmed(false); setPromotionOpen(true); promotionDialog.current?.showModal(); }}>{promote.isPending ? "Promoting revision…" : "Promote candidate revision"}</button>}<RequestError error={promotionOpen ? null : promote.error} />{promote.isSuccess && <p role="status">Candidate promoted. Previous extraction history remains available.</p>}</>}
      </section><RequestError error={sourceError} /><div hidden={tab !== "Question assembly" && tab !== "Answer pairing"} className="extraction-reading-grid" data-reading-pane={readingPane}><div className="extraction-reading-tabs" role="tablist" aria-label="Reading pane">{["Source", "Question", "Answer"].map(name => <button key={name} role="tab" aria-selected={readingPane === name} className={control} onClick={() => setReadingPane(name)}>{name}</button>)}</div><section className="space-y-3 extraction-assembled"><h2 className="font-semibold">Complete questions and answers</h2><RequestError error={questions.error} retry={() => void questions.refetch()} />{questions.isFetching && <p role="status">Loading complete questions…</p>}{questions.data?.items.length === 0 && <p>This revision contains no question roots.</p>}{questions.data?.items.map(question => <Question key={question.question_id} question={question} open={open} openDocument={openDocument} />)}{questions.data && <Pagination page={questionPage} total={questions.data.total} size={questions.data.page_size} name="questions" change={setQuestionPage} />}</section>{sourceDocument !== null && <SourcePage document={sourceDocument} page={sourcePage} pageCount={revision.data.source_documents.find(item => item.id === sourceDocument)?.page_count ?? previous.data?.source_documents.find(item => item.id === sourceDocument)?.page_count ?? (sourceDocument === document?.id ? document.page_count : null)} change={setSourcePage} />}</div>
        <div hidden={tab === "Revision differences"}><ExtractionEvidence key={revisionId} revision={revision.data} admin={admin} onCorrected={id => { setSelectedRevision(id); setQuestionPage(1); review.reset(); promote.reset(); void refresh(); }} /></div>
        {tab === "Revision differences" && comparison === null && <p>Select a previous revision above to compare the complete question and answer trees.</p>}{comparison !== null && <section hidden={tab !== "Revision differences"} className={panel}><h2 className="font-semibold">Previous revision comparison · {comparison}</h2><RequestError error={previous.error} retry={() => void previous.refetch()} />{previous.isFetching && <p role="status">Loading comparison…</p>}{previous.data && <><p>Digest: <span className="break-all">{previous.data.content_digest}</span></p><p>{previous.data.content_digest === revision.data.content_digest ? "The complete revision content is unchanged." : "Content differs. Compare question and answer trees before promotion."}</p>{previous.data.questions.map(question => <Question key={question.question_id} question={question} open={open} openDocument={openDocument} />)}</>}</section>}
      </>}
    </>}
    <dialog ref={promotionDialog} onClose={() => setPromotionOpen(false)} className="review-dialog" aria-labelledby="promotion-title"><h2 id="promotion-title">Review candidate promotion</h2><p>Before: current revision {document?.current_revision_id ?? "None"}. After: candidate revision {revisionId}.</p><p>The current revision and its reviews remain in history. Classification based on changed content requires regeneration and review.</p><p>Readiness: {revision.data?.quality.issues.length ? `${revision.data.quality.issues.length} quality issues require review; backend readiness gates remain decisive.` : "No generated quality issues recorded. Reviewed quality and source gates still apply."}</p><label><input type="checkbox" checked={promotionConfirmed} onChange={event => setPromotionConfirmed(event.target.checked)} /> I compared the complete candidate, original sources, quality reviews and revision differences.</label><RequestError error={promote.error} /><div className="flex gap-3 mt-4"><button type="button" disabled={!promotionConfirmed || promote.isPending} onClick={() => promote.mutate(undefined, { onSuccess: () => promotionDialog.current?.close() })}>Confirm promotion</button><button type="button" disabled={promote.isPending} onClick={() => promotionDialog.current?.close()}>Keep reviewing</button></div></dialog>
  </div>;
}
