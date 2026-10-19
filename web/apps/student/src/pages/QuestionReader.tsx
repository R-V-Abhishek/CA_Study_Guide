import { lazy, Suspense, useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiRequest, accountKey, type components, type PublishedQuestion, type ExtractionQuestionPart, type ExtractionAnswerPart } from '@caf/api-client';
import { getData, mode, usePapers } from '../lib/data';
import { demoLink, isDemoMode } from '../lib/demo';
import { internalReturn } from '../lib/url';
import { PageState } from '../components/PageState';
import { PublishedImage } from '../components/PublishedImage';
import { Dialog } from '../../../../packages/workspace/Dialog';
import { rememberDestination } from '../lib/navigation';
import { QuestionPages } from '../components/QuestionPages';
const QuestionText = lazy(() => import('../components/ExtractedContent').then(module => ({ default: module.QuestionText })));
const AnswerText = lazy(() => import('../components/ExtractedContent').then(module => ({ default: module.AnswerText })));

const marksText = (marks: number | null | undefined) => marks == null ? 'Marks not available' : `${marks} marks`;
type BaselineQuality = {
  baseline?: { release_id: string; manifest_hash: string; scope: 'study_and_review'; applicability_status: 'source_evidence_only_target_review_required' };
  unresolved_parts?: string[];
};
function BaselineProvenance({ question }: { question: PublishedQuestion }) {
  const { baseline, unresolved_parts = [] } = question.extraction_quality as BaselineQuality;
  if (!baseline) return null;
  const unresolvedCount = new Set(unresolved_parts).size;
  return <section aria-label="Baseline provenance" className="space-y-1 study-meta">

    {unresolvedCount > 0 && <p role="status">Topic labels remain unresolved for {unresolvedCount} {unresolvedCount === 1 ? 'part' : 'parts'}.</p>}
    {baseline.applicability_status === 'source_evidence_only_target_review_required' && <p>May 2027 applicability review pending.{question.content.paper_id === 's2023.P5' && ' P5 includes older-edition material; check the prescribed syllabus before relying on it for the exam.'}</p>}
  </section>;
}
function allQuestionParts(parts: ExtractionQuestionPart[]): ExtractionQuestionPart[] { return parts.flatMap(part => [part, ...allQuestionParts(part.parts ?? [])]); }
function allAnswerParts(parts: ExtractionAnswerPart[]): ExtractionAnswerPart[] { return parts.flatMap(part => [part, ...allAnswerParts(part.parts ?? [])]); }
export function QuestionReader() {
  const { questionId = '' } = useParams();
  const [params] = useSearchParams();
  const location = useLocation();
  const selected = params.get('part');
  const [reveal, setReveal] = useState(false);
  const [presentation, setPresentation] = useState<'source' | 'text'>('source');
  const [sourceOpen, setSourceOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [sourceId, setSourceId] = useState('');
  const [page, setPage] = useState(0);
  const query = useQuery({ queryKey: ['published-question', mode(), questionId], queryFn: ({ signal }) => getData<PublishedQuestion>(`/api/v1/questions/${encodeURIComponent(questionId)}`, signal) });
  const papers = usePapers();
  const settings = useQuery({ queryKey: ['settings', accountKey()], enabled: !isDemoMode(), queryFn: () => apiRequest<components['schemas']['ProfileSettings']>('/api/v1/me/settings') });
  useEffect(() => { setReveal(false); setPresentation('source'); setSourceOpen(false); setDetailsOpen(false); setOutlineOpen(false); setSourceId(''); setPage(0); }, [questionId]);
  useEffect(() => { if (query.data && selected) document.getElementById(`part-${selected}`)?.scrollIntoView({ block: 'nearest' }); }, [query.data, selected]);
  const data = query.data;
  const original = presentation === 'source' && Boolean(data?.question_pages?.length);
  const current = `${location.pathname}${location.search}`;
  useEffect(() => {
    if (!data) return;
    const paper = papers.data?.find(item => item.id === data.content.paper_id)?.name
      ?? settings.data?.available_papers.find(item => item.id === data.content.paper_id)?.name ?? 'Paper name not available';
    const attempt = data.content.source_attempt_id
      ? settings.data?.available_attempts.find(item => item.id === data.content.source_attempt_id)?.label ?? 'Attempt name not available'
      : 'Undated collection';
    const topic = data.covered_subtopics[0]?.path.map(node => node.name).join(' / ');
    rememberDestination({ path: current, title: data.content.display_label, paper,
      breadcrumb: [topic, attempt, data.content.source_family.replace(/_/g, ' ')].filter(Boolean).join(' / ') });
  }, [data, current, papers.data, settings.data]);
  const parts = allQuestionParts(data?.content.parts ?? []);
  const spans = data ? [...data.content.source_spans, ...parts.flatMap(part => part.source_spans), ...allAnswerParts(data.content.answers ?? []).flatMap(part => part.source_spans)] : [];
  const source = data?.sources.find(item => String(item.id) === sourceId) ?? data?.sources[0];
  const referencedPages = source ? [...new Set(spans.filter(span => span.document_sha256 === source.sha256).flatMap(span => Array.from({ length: span.page_end - span.page_start + 1 }, (_, index) => span.page_start + index)))].sort((a, b) => a - b) : [];
  const sourcePages = source?.page_count ? Array.from({ length: source.page_count }, (_,index) => index + 1) : referencedPages;
  const validPage = sourcePages.includes(page) ? page : referencedPages[0] ?? sourcePages[0] ?? 1;
  const returnTo = internalReturn(params.get('return'));
  const originName = returnTo.startsWith('/syllabus') || /^\/papers\//.test(returnTo) ? 'topic' : returnTo.startsWith('/plan') ? 'plan' : returnTo.startsWith('/revision') ? 'revision' : 'questions';
  const outline = <><h2 className="font-semibold">Parts</h2><nav aria-label="Question parts" className="space-y-2">{parts.map(part => <a className="topic-link block" key={part.id} href={`#part-${part.id}`} onClick={() => setOutlineOpen(false)}>{part.label}</a>)}</nav><h2 className="font-semibold">Covers {new Set(data?.covered_subtopics.map(node => node.node_id)).size} subtopics</h2>{data?.covered_subtopics.map(node => <p key={node.node_id}><Link className="topic-link" to={demoLink(`/syllabus?${new URLSearchParams({ paper: data.content.paper_id, node: node.node_id, return: current })}`)}>{node.path.map(path => path.name).join(' / ') || node.name}</Link></p>)}<button className="action" onClick={() => setSourceOpen(true)}>View source</button><button onClick={() => setDetailsOpen(true)}>Content details</button>{data?.covered_subtopics[0] && <Link className="topic-link" to={demoLink(`/syllabus?${new URLSearchParams({ paper: data.content.paper_id, node: data.covered_subtopics[0].node_id, tab: 'notes', return: current })}`)}>My topic notes</Link>}<p className="study-meta">Reading does not change your syllabus progress.</p></>;
  return <div className="space-y-5"><Link className="topic-link" to={demoLink(returnTo)}>← Back to {originName}</Link><PageState loading={query.isPending} refreshing={query.isFetching && Boolean(data)} error={query.error} retry={() => query.refetch()} />{data && <><header className="space-y-2"><p className="study-meta">{papers.data?.find(item => item.id === data.content.paper_id)?.name ?? settings.data?.available_papers.find(item => item.id === data.content.paper_id)?.name ?? 'Paper name not available'} · {settings.data?.available_attempts.find(item => item.id === data.content.source_attempt_id)?.label ?? data.content.source_attempt_id ?? 'Undated collection'}</p><h1 className="page-title">{data.content.display_label}</h1><p>{data.content.source_family.replace(/_/g,' ')} · {marksText(data.marks.whole_question_marks)} · {data.content.answer_status === 'complete' ? 'Complete answer' : data.content.answer_status === 'partial' ? 'Partial answer' : 'No reviewed answer'}</p>{data.marks.issues.length > 0 && <p className="study-meta">Some marks or question choices still need review. See Content details.</p>}<BaselineProvenance question={data} /><div className="study-meta"><p>Topic labels verified by {data?.verification_count} students</p>{Boolean(data?.open_disputes) && <p role="status">Topic labels are disputed. The current publication remains visible.</p>}</div></header><div className="reader-columns"><article className="reader-body"><div className="study-tabs" role="tablist" aria-label="Question presentation"><button role="tab" aria-selected={original} disabled={!data.question_pages?.length} onClick={() => setPresentation('source')}>Original pages</button><button role="tab" aria-selected={!original} onClick={() => setPresentation('text')}>Extracted text</button></div>{original && data.question_pages?.length ? <><p className="study-meta">These original source pages may include neighboring questions and suggested answers. Recorded question boundaries still need review.</p><QuestionPages pages={data.question_pages} label="Question" revision={data.snapshot_id} /></> : <Suspense fallback={<p role="status">Loading question text…</p>}><QuestionText data={data} selected={selected} /></Suspense>}
    <section id="answer" className="reader-part"><h2>Answer</h2>{data.content.answer_status === 'missing' && !data.content.mcq.some(mcq => mcq.key) ? <p>No reviewed answer is available for this question.</p> : <><button className="action" aria-expanded={reveal} onClick={() => setReveal(!reveal)}>{reveal ? 'Hide answer' : 'Reveal answer'}</button>{reveal && <div className="mt-6">{data.content.answer_status === 'partial' && <p role="status">This answer is partial. Some parts have no reviewed answer.</p>}{original && data.answer_pages?.length ? <QuestionPages pages={data.answer_pages} label="Answer" revision={data.snapshot_id} /> : <Suspense fallback={<p role="status">Loading answer text…</p>}><AnswerText data={data} /></Suspense>}</div>}</>}</section><div className="reader-toolbar"><a className="topic-link" href="#answer">Go to answer</a><button onClick={() => setSourceOpen(true)}>View source</button><button aria-expanded={outlineOpen} onClick={() => setOutlineOpen(true)}>Topics and outline</button></div></article><aside className="reader-aside"><details><summary>Topics and outline</summary>{outline}</details></aside></div>
    <Dialog open={outlineOpen} title="Parts and evidence" onClose={() => setOutlineOpen(false)}>{outline}</Dialog>
    <Dialog open={detailsOpen} title="Content details" onClose={() => setDetailsOpen(false)}><details><summary>Marks and choice review details</summary>{data.marks.issues.map((issue, index) => <p key={index}>{issue}</p>)}</details><p>Question review: {data.content.question_status} · Readability {data.content.readability_status} · Answer pairing {data.content.pairing_status}</p><p>Offered: {marksText(data.marks.offered_marks)} · Selectable: {marksText(data.marks.selectable_marks)}</p><details><summary>Technical details</summary>{(data.extraction_quality as BaselineQuality).baseline && <p className="break-all">Adopted baseline {(data.extraction_quality as BaselineQuality).baseline?.release_id} · Baseline manifest SHA-256 {(data.extraction_quality as BaselineQuality).baseline?.manifest_hash}</p>}<p>Snapshot {data.snapshot_id} · Classification revision {data.classification_revision_id} · Extraction revision {data.extraction_revision_id} · Taxonomy {data.taxonomy_version_id}</p>{data.sources.map(item => <p className="break-all" key={item.id}>{item.title} · SHA-256 {item.sha256}</p>)}</details></Dialog>
    <Dialog open={sourceOpen} title="Source and pages" className="reader-source" onClose={() => setSourceOpen(false)}>{source ? <div className="space-y-4"><label className="block">Source <select value={String(source.id)} onChange={event => { setSourceId(event.target.value); setPage(0); }}>{data.sources.map(item => <option key={item.id} value={String(item.id)}>{item.title ?? 'Official source'}</option>)}</select></label><p>{source.title} · {source.doc_type_id?.replace(/_/g,' ') ?? 'Source type not available'}</p><div className="controls"><label>Page <select value={validPage} onChange={event => setPage(Number(event.target.value))}>{(sourcePages.length ? sourcePages : [1]).map(number => <option key={number} value={number}>Page {number}</option>)}</select></label><button disabled={sourcePages.indexOf(validPage) <= 0} onClick={() => setPage(sourcePages[sourcePages.indexOf(validPage) - 1])}>Previous page</button><button disabled={sourcePages.indexOf(validPage) >= sourcePages.length - 1} onClick={() => setPage(sourcePages[sourcePages.indexOf(validPage) + 1])}>Next page</button></div>{isDemoMode() ? <p>Source page previews are available for authenticated published content.</p> : <PublishedImage url={source.page_url.replace('{page}', String(validPage))} label={`Published question source page ${validPage}`} />}{/^\/api\/v1\/published-sources\//.test(source.url) && !isDemoMode() && <a className="topic-link" href={source.url} target="_blank" rel="noreferrer">Open PDF</a>}</div> : <p>No reviewed source pages are available.</p>}</Dialog>
  </>}</div>;
}
