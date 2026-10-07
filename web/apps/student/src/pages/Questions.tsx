import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { QuestionPage } from '@caf/api-client';
import { getData, mode, usePapers } from '../lib/data';
import { demoLink } from '../lib/demo';
import { useUrlState } from '../lib/url';
import { PageState } from '../components/PageState';

export function Questions() {
  const { params, set, search } = useUrlState();
  const q = params.get('q') ?? '';
  const pageValue = Number(params.get('page'));
  const page = Number.isSafeInteger(pageValue) && pageValue >= 1 ? pageValue : 1;
  const papers = usePapers();
  const filters = new URLSearchParams();
  for (const key of ['paper_id', 'subtopic_id', 'attempt_id', 'source_family', 'answer_status']) { const value = params.get(key); if (value) filters.set(key, value); }
  filters.set('page', String(page)); filters.set('page_size', '20');
  if (q.trim()) filters.set('q', q.trim());
  if (params.get('include_notes') === 'true') filters.set('include_notes', 'true');
  const useSearch = q.trim().length > 0;
  const url = `/api/v1/${useSearch ? 'search' : 'questions'}?${filters}`;
  const query = useQuery({ queryKey: ['published-questions', mode(), url], queryFn: () => getData<QuestionPage>(url) });
  const change = (key: string, value: string) => set({ [key]: value, page: '' });
  return <div className="space-y-5"><h1 className="page-title">Published questions</h1><p>Read complete reviewed questions, including shared cases, all parts and available answers.</p>
    <div className="controls"><label>Search questions <input aria-label="Search questions" value={q} onChange={event => change('q', event.target.value)} /></label><label>Paper <select aria-label="Paper" value={params.get('paper_id') ?? 'all'} onChange={event => change('paper_id', event.target.value)}><option value="all">All papers</option>{papers.data?.map(paper => <option key={paper.id} value={paper.id}>{paper.code} — {paper.name}</option>)}</select></label><label>Subtopic ID <input value={params.get('subtopic_id') ?? ''} onChange={event => change('subtopic_id', event.target.value)} /></label><label>Attempt <input aria-label="Attempt" placeholder="e.g. 2026-05" value={params.get('attempt_id') ?? ''} onChange={event => change('attempt_id', event.target.value)} /></label><label>Source family <input aria-label="Source family" value={params.get('source_family') ?? ''} onChange={event => change('source_family', event.target.value)} /></label><label>Answer status <select aria-label="Answer status" value={params.get('answer_status') ?? 'all'} onChange={event => change('answer_status', event.target.value)}><option value="all">All answers</option><option value="complete">Complete</option><option value="partial">Partial</option><option value="missing">Missing</option></select></label><label><input type="checkbox" checked={params.get('include_notes') === 'true'} onChange={event => change('include_notes', event.target.checked ? 'true' : '')} /> Include my private notes in search</label></div>
    <PageState loading={query.isPending} error={query.error ?? papers.error} retry={() => { query.refetch(); papers.refetch(); }} />
    {query.data && <><p>{query.data.total} published questions · Page {query.data.page}</p>{!query.data.items.length && <p className="card">No published questions match these filters.</p>}<div className="space-y-3">{query.data.items.map(item => <article key={item.question_id} className="card space-y-2"><h2><Link className="topic-link font-bold" to={demoLink(`/questions/${encodeURIComponent(item.question_id)}?return=${encodeURIComponent(`/questions${search}`)}`)}>{item.display_label}</Link></h2><p>{item.paper_id} · {item.attempt_id ?? 'Undated collection'} · {item.source_family} · Answer {item.answer_status}</p><p className="whitespace-pre-wrap">{(item.common_stem || item.question_text).slice(0, 500)}</p>{item.covered_subtopics.map(node => <p key={node.node_id} className="text-sm">{node.path.map(path => path.name).join(' / ') || node.name}</p>)}</article>)}</div>{query.data.notes && <section className="card space-y-2"><h2 className="font-bold">My private notes</h2>{query.data.notes.length ? query.data.notes.map(note => <p className="whitespace-pre-wrap" key={note.node_id}>{note.node_id}: {note.content}</p>) : <p>No matching notes.</p>}</section>}<div className="controls"><button className="action" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>Previous page</button><button className="action" disabled={page * query.data.page_size >= query.data.total} onClick={() => set({ page: String(page + 1) })}>Next page</button></div></>}
  </div>;
}
