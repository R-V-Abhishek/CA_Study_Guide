import { useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { PublishedQuestion, ExtractionQuestionPart, ExtractionAnswerPart } from '@caf/api-client';
import { getData, mode } from '../lib/data';
import { demoLink, isDemoMode } from '../lib/demo';
import { internalReturn } from '../lib/url';
import { PageState } from '../components/PageState';
import { PublishedImage } from '../components/PublishedImage';

const marksText = (marks: number | null | undefined) => marks == null ? 'Marks unknown' : `${marks} marks`;
function allQuestionParts(parts: ExtractionQuestionPart[]): ExtractionQuestionPart[] { return parts.flatMap(part => [part, ...allQuestionParts(part.parts ?? [])]); }
function allAnswerParts(parts: ExtractionAnswerPart[]): ExtractionAnswerPart[] { return parts.flatMap(part => [part, ...allAnswerParts(part.parts ?? [])]); }
function Content({ text }: { text: string }) { return <div className="prose dark:prose-invert max-w-none whitespace-pre-wrap"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>; }
function Parts({ parts, selected }: { parts: ExtractionQuestionPart[]; selected: string | null }) {
  return <div className="space-y-4">{parts.map(part => <section id={`part-${part.id}`} key={part.id} data-selected={part.id === selected} className={`rounded-lg border p-4 space-y-2 ${part.id === selected ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950' : 'border-stone-200 dark:border-stone-700'}`}><h3 className="font-bold">{part.label} · {marksText(part.marks)}{part.id === selected && <span> · Selected part</span>}</h3><Content text={part.question_text} /><Parts parts={part.parts ?? []} selected={selected} /></section>)}</div>;
}
function Answers({ answers }: { answers: ExtractionAnswerPart[] }) {
  return <div className="space-y-4">{answers.map(answer => <section key={answer.id} className="space-y-2">{answer.question_part_id && <p className="text-sm">Answer for {answer.question_part_id}</p>}<Content text={answer.answer_text} /><Answers answers={answer.parts ?? []} /></section>)}</div>;
}
export function QuestionReader() {
  const { questionId = '' } = useParams();
  const [params] = useSearchParams();
  const location = useLocation();
  const selected = params.get('part');
  const [reveal, setReveal] = useState(false);
  const [sourcePage, setSourcePage] = useState('');
  const query = useQuery({ queryKey: ['published-question', mode(), questionId], queryFn: () => getData<PublishedQuestion>(`/api/v1/questions/${encodeURIComponent(questionId)}`) });
  useEffect(() => { setReveal(false); setSourcePage(''); }, [questionId]);
  useEffect(() => { if (query.data && selected) document.getElementById(`part-${selected}`)?.scrollIntoView({ block: 'nearest' }); }, [query.data, selected]);
  const data = query.data;
  const current = `${location.pathname}${location.search}`;
  const allocation = data?.marks.allocations.find(part => part.part_id === selected);
  const spans = data ? [...data.content.source_spans, ...allQuestionParts(data.content.parts ?? []).flatMap(part => part.source_spans), ...allAnswerParts(data.content.answers ?? []).flatMap(part => part.source_spans)] : [];
  return <div className="space-y-5"><Link className="topic-link" to={demoLink(internalReturn(params.get('return')))}>← Return</Link><h1 className="page-title">{data?.content.display_label ?? 'Question reader'}</h1><PageState loading={query.isPending} error={query.error} retry={() => query.refetch()} />{data && <>
    <section className="card space-y-3"><p>{data.content.paper_id} · {data.content.source_attempt_id ?? 'Undated collection'} · {data.content.source_family}</p><p>Whole question: {marksText(data.marks.whole_question_marks)} · Offered: {marksText(data.marks.offered_marks)} · Selectable: {marksText(data.marks.selectable_marks)}</p>{selected && <p>Selected part: {marksText(allocation?.marks)}{allocation && <> · Attributed: {allocation.node_shares.map(share => `${data.covered_subtopics.find(node => node.node_id === share.node_id)?.name ?? share.node_id}: ${marksText(share.attributed_marks)}`).join('; ')}</>}</p>}{data.marks.issues.map((issue, index) => <p className="text-amber-700 dark:text-amber-300" key={index}>{issue}</p>)}<p>Topic labels: {data.verification_count} verifications · {data.open_disputes} open disputes</p><p>Extraction: {data.content.review_status} · Questions {data.content.question_status} · Readability {data.content.readability_status} · Answer pairing {data.content.pairing_status}</p><p className="text-sm">Snapshot {data.snapshot_id} · Classification revision {data.classification_revision_id} · Extraction revision {data.extraction_revision_id} · Taxonomy {data.taxonomy_version_id}</p></section>
    <section className="card space-y-4"><h2 className="font-bold">Complete question</h2>{data.content.common_stem && <div><h3 className="font-semibold">Shared case / stem</h3><Content text={data.content.common_stem} /></div>}{data.content.question_text && <Content text={data.content.question_text} />}<Parts parts={data.content.parts ?? []} selected={selected} />{data.content.choices.length > 0 && <div><h3 className="font-semibold">Choice structure</h3>{data.content.choices.map((choice, index) => <p key={index}>{choice.label}: {choice.role}{choice.or_group && ` · OR group ${choice.or_group}`} · {marksText(choice.marks)}</p>)}</div>}{data.content.mcq.map(mcq => <fieldset key={mcq.part_id}><legend className="font-semibold">Options for {mcq.part_id}</legend><ol className="list-[upper-alpha] pl-6">{mcq.options.map((option, index) => <li key={index}><Content text={option} /></li>)}</ol></fieldset>)}{data.assets.map(asset => <figure className="space-y-2" key={asset.id}>{isDemoMode() ? <p>Source asset preview is available for authenticated published content.</p> : <PublishedImage url={asset.url} label={`${asset.kind}, page ${asset.page}`} />}<figcaption>{asset.kind} · page {asset.page}{asset.concerns.length > 0 && ` · ${asset.concerns.join('; ')}`}</figcaption></figure>)}</section>
    <section className="card space-y-3"><h2 className="font-bold">Answer</h2><p>Answer status: {data.content.answer_status}</p>{data.content.answer_status === 'missing' && !data.content.mcq.some(mcq => mcq.key) ? <p>No published answer is available.</p> : <><button className="action" aria-expanded={reveal} onClick={() => setReveal(!reveal)}>{reveal ? 'Hide answer' : 'Reveal answer'}</button>{reveal && <>{data.content.answer_status === 'partial' && <p className="text-amber-700 dark:text-amber-300">This answer is partial. Some parts have no reviewed answer.</p>}<Answers answers={data.content.answers ?? []} />{data.content.mcq.filter(mcq => mcq.key).map(mcq => <p key={mcq.part_id}>Key for {mcq.part_id}: {mcq.key}</p>)}</>}</>}</section>
    <section className="card space-y-2"><h2 className="font-bold">Covered subtopics</h2>{data.covered_subtopics.length ? data.covered_subtopics.map(node => <p key={node.node_id}><Link className="topic-link" to={demoLink(`/papers/${encodeURIComponent(data.content.paper_id)}/${encodeURIComponent(node.node_id)}?return=${encodeURIComponent(current)}`)}>{node.path.map(path => path.name).join(' / ') || node.name}</Link></p>) : <p>No applicable topic labels are published.</p>}<p className="text-sm">Reading does not change your syllabus progress.</p></section>
    <section className="card space-y-3"><h2 className="font-bold">Source and pages</h2>{data.sources.map(source => <div className="space-y-2" key={source.id}><p>{source.title ?? `Source ${source.id}`} · {source.doc_type_id ?? 'Type unavailable'} · {source.attempt_id ?? 'Undated'}<br /><span className="break-all text-xs">SHA-256 {source.sha256}</span></p>{/^\/api\/v1\/published-sources\//.test(source.url) && !isDemoMode() && <a className="topic-link" href={source.url} target="_blank" rel="noreferrer">Open published source</a>}<div className="controls">{spans.filter(span => span.document_sha256 === source.sha256).flatMap(span => Array.from({ length: span.page_end - span.page_start + 1 }, (_, index) => span.page_start + index)).filter((page, index, pages) => pages.indexOf(page) === index).map(page => <button key={page} className="topic-link" onClick={() => setSourcePage(source.page_url.replace('{page}', String(page)))}>View page {page}</button>)}</div></div>)}{sourcePage && (isDemoMode() ? <p>Source page previews are available for authenticated published content.</p> : <PublishedImage url={sourcePage} label="Published question source page" />)}</section>
  </>}</div>;
}
