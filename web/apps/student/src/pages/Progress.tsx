import { Link } from 'react-router-dom';
import { useQueries } from '@tanstack/react-query';
import { usePapers, getTree, mode, formatPct, importance } from '../lib/data';
import { useUrlState } from '../lib/url';
import { demoLink } from '../lib/demo';
import { PageState } from '../components/PageState';
export function Progress() {
  const { params, set, search } = useUrlState();
  const filter = params.get('status') ?? 'all';
  const weak = params.get('weak') === 'true' || filter === 'weak';
  const sort = params.get('sort') ?? 'code';
  const papers = usePapers();
  const results = useQueries({ queries: (papers.data ?? []).map(p => ({ queryKey: ['paper-tree', mode(), p.id], queryFn: () => getTree(p.id) })) });
  const pending = results.some(result => result.isPending);
  const failed = results.some(result => result.isError);
  const data = (papers.data ?? []).map((paper, index) => ({ paper, query: results[index] })).sort((a, b) => {
    const coverage = sort === 'coverage_asc' ? a.paper.raw_progress_pct - b.paper.raw_progress_pct : sort === 'coverage_desc' ? b.paper.raw_progress_pct - a.paper.raw_progress_pct : 0;
    return coverage || a.paper.code.localeCompare(b.paper.code) || a.paper.id.localeCompare(b.paper.id);
  });
  const total = papers.data?.reduce((sum, paper) => sum + paper.total_subtopics, 0) ?? 0;
  const done = papers.data?.reduce((sum, paper) => sum + paper.completed_subtopics, 0) ?? 0;
  const matches = data.some(({ query }) => query?.data?.chapters.some(ch => ch.topics.some(topic => topic.subtopics.some(s => (filter === 'all' || filter === 'weak' || s.status === filter) && (!weak || s.weak)))));
  return <div className="space-y-5"><h1 className="page-title">Coverage</h1><PageState loading={papers.isPending} error={papers.error} retry={() => papers.refetch()} />
    {papers.data && !pending && !failed && <p className="card">{done} / {total} topics completed · {formatPct(total ? done / total * 100 : 0)}</p>}
    {pending && <p role="status">Loading paper coverage…</p>}{failed && <p role="alert">Coverage is incomplete because some papers failed to load. Complete totals are unavailable.</p>}
    <div className="controls"><label>Status <select aria-label="Status" value={filter} onChange={e => set({ status: e.target.value })}><option value="all">All statuses</option><option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="done">Done</option></select></label><label><input type="checkbox" checked={weak} onChange={e => set({ weak: e.target.checked ? 'true' : '', status: filter === 'weak' ? 'all' : filter })} /> Weak only</label><label>Sort <select aria-label="Sort" value={sort} onChange={e => set({ sort: e.target.value })}><option value="code">Paper code</option><option value="coverage_asc">Lowest coverage</option><option value="coverage_desc">Highest coverage</option></select></label></div>
    {papers.data && !papers.data.length && <p className="card">No papers available.</p>}
    {!pending && !failed && papers.data?.length && !matches ? <p className="card">{total ? 'No results match these filters.' : 'No subtopics available.'}</p> : null}
    {data.map(({ paper, query }) => <section className="card space-y-3" key={paper.id}><h2 className="font-bold">{paper.code} — {paper.name} · {formatPct(paper.raw_progress_pct)}</h2><PageState loading={query?.isPending} error={query?.error} retry={() => query?.refetch()} />{query?.data?.chapters.map(ch => {
      const subs = ch.topics.flatMap(topic => topic.subtopics).filter(s => (filter === 'all' || filter === 'weak' || s.status === filter) && (!weak || s.weak)).sort((a, b) => a.seq - b.seq || a.id.localeCompare(b.id));
      return subs.length ? <details key={ch.id} open><summary className="font-semibold">{ch.name}</summary>{subs.map(s => <p key={s.id} className="py-2"><Link className="topic-link" to={demoLink(`/papers/${paper.id}/${s.id}?return=${encodeURIComponent(`/progress${search}`)}`)}>{s.name}</Link> · {s.status.replace(/_/g, ' ')} · Importance {importance(s.importance)}</p>)}</details> : null;
    })}</section>)}
  </div>;
}
