import { Link } from 'react-router-dom';
import { usePapers, formatPct, importance } from '../lib/data';
import { demoLink } from '../lib/demo';
import { useUrlState } from '../lib/url';
import { PageState } from '../components/PageState';
export function Papers() {
  const { params, set } = useUrlState();
  const group = params.get('group') ?? 'all';
  const sort = params.get('sort') ?? 'group';
  const query = usePapers();
  const papers = query.data ?? [];
  const filtered = papers.filter(p => group === 'all' || String(p.group_no) === group).sort((a, b) => {
    const difference = sort === 'coverage_asc' ? (a.weighted_coverage_pct ?? a.raw_progress_pct) - (b.weighted_coverage_pct ?? b.raw_progress_pct) : sort === 'importance_desc' ? (b.average_importance ?? -1) - (a.average_importance ?? -1) : (a.group_no ?? 99) - (b.group_no ?? 99);
    return difference || a.code.localeCompare(b.code) || a.id.localeCompare(b.id);
  });
  return <div className="space-y-5"><h1 className="page-title">Papers Overview</h1><div className="controls"><label>Group <select aria-label="Group" value={group} onChange={e => set({ group: e.target.value })}><option value="all">All groups</option><option value="1">Group 1</option><option value="2">Group 2</option></select></label><label>Sort <select aria-label="Sort" value={sort} onChange={e => set({ sort: e.target.value })}><option value="group">By group</option><option value="coverage_asc">Lowest coverage first</option><option value="importance_desc">Highest importance</option></select></label></div>
    <PageState loading={query.isPending} error={query.error} retry={() => query.refetch()} />
    {query.data && !filtered.length && <p className="card">{papers.length ? 'No results match these filters.' : 'No papers available.'}</p>}
    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">{filtered.map(p => <Link className="card space-y-3 hover:border-indigo-400" key={p.id} to={demoLink(`/papers/${p.id}`)}><h2 className="font-bold">{p.code} — {p.name}</h2><p>Group {p.group_no ?? 'Unavailable'}</p><p>{p.completed_subtopics} / {p.total_subtopics} completed · {formatPct(p.raw_progress_pct)}</p><p>Weighted coverage: {formatPct(p.weighted_coverage_pct)}</p><p>Average importance: {importance(p.average_importance)}</p><p>{p.revision_due_count} revisions due · {p.weak_topic_count} weak topics</p></Link>)}</div>
  </div>;
}
