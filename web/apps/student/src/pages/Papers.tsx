import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { QuestionPage } from '@caf/api-client';
import { usePapers, getData, mode } from '../lib/data';
import { demoLink } from '../lib/demo';
import { useUrlState } from '../lib/url';
import { PageState } from '../components/PageState';
import type { PaperSummary } from '../lib/contracts';
function PaperPanel({ paper }: { paper: PaperSummary }) {
  const questions = useQuery({ queryKey: ['reviewed-question-count', mode(), paper.id], queryFn: () => getData<QuestionPage>(`/api/v1/questions?paper_id=${encodeURIComponent(paper.id)}&page=1&page_size=1`) });
  return <article className="card space-y-3"><p className="study-meta">{paper.code}</p><h3 className="font-semibold">{paper.name}</h3><p>{paper.completed_subtopics} / {paper.total_subtopics} completed</p><progress className="study-bar" aria-label={`${paper.name} progress`} max={paper.total_subtopics || 1} value={paper.completed_subtopics} /><p className="study-meta">Reviewed questions: {questions.data?.total ?? 'Not available'} · Revisions due: {paper.revision_due_count ?? 'Not available'}</p><div className="controls"><Link className="primary-action inline-flex" to={demoLink(`/syllabus?paper=${encodeURIComponent(paper.id)}`)}>Open syllabus</Link><Link className="topic-link" to={demoLink(`/questions?paper_id=${encodeURIComponent(paper.id)}`)}>Browse questions</Link></div></article>;
}
export function Papers() {
  const { params, set } = useUrlState();
  const group = params.get('group') ?? 'all';
  const sort = params.get('sort') ?? 'group';
  const query = usePapers();
  const papers = query.data ?? [];
  const filtered = papers.filter(paper => group === 'all' || String(paper.group_no) === group).sort((a,b) => (sort === 'coverage_asc' ? a.raw_progress_pct - b.raw_progress_pct : sort === 'revision_desc' ? b.revision_due_count - a.revision_due_count : 0) || a.code.localeCompare(b.code));
  return <div className="space-y-5"><h1 className="page-title">Papers</h1><p>Open a paper’s syllabus, reviewed questions and personal progress.</p><div className="controls"><label>Group <select aria-label="Group" value={group} onChange={event => set({ group: event.target.value })}><option value="all">All groups</option><option value="1">Group 1</option><option value="2">Group 2</option></select></label><label>Sort <select aria-label="Sort" value={sort} onChange={event => set({ sort: event.target.value })}><option value="group">Paper order</option><option value="coverage_asc">Least completed</option><option value="revision_desc">Most revisions due</option></select></label></div><PageState loading={query.isPending} refreshing={query.isFetching && Boolean(query.data)} error={query.error} retry={() => query.refetch()} />{query.data && !filtered.length && <p className="card">{papers.length ? 'No results match these filters.' : 'No papers available.'}</p>}{[1,2,null].map(groupNumber => { const items = filtered.filter(paper => paper.group_no === groupNumber); return items.length ? <section key={groupNumber ?? 'other'} className="space-y-3"><h2 className="text-xl font-semibold">{groupNumber ? `Group ${groupNumber}` : 'Other papers'}</h2><div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">{items.map(paper => <PaperPanel key={paper.id} paper={paper} />)}</div></section> : null; })}</div>;
}
