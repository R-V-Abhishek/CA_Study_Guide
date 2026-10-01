import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getTree, mode, importance } from '../lib/data';
import { demoLink } from '../lib/demo';
import { useUrlState } from '../lib/url';
import { PageState } from '../components/PageState';
import { SubtopicDetail } from '../components/SubtopicDetail';
import type { SubtopicNode } from '../lib/contracts';
export function PaperDetail() {
  const { paperId = '', nodeId } = useParams();
  const { params, set, search } = useUrlState();
  const returnPath = params.get('return');
  const overview = params.get('overview');
  const overviewPath = overview && /^\/papers(\?|$)/.test(overview) ? overview : '/papers';
  const backPath = returnPath && /^\/(progress|plan|revision|papers)(\?|\/|$)/.test(returnPath) ? returnPath : `/papers/${paperId}${search}`;
  const filter = params.get('status') ?? 'all';
  const weak = params.get('weak') === 'true' || filter === 'weak';
  const sort = params.get('sort') ?? 'importance';
  const text = params.get('search') ?? '';
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const query = useQuery({ queryKey: ['paper-tree', mode(), paperId], queryFn: () => getTree(paperId) });
  const tree = query.data;
  const chapters = tree?.chapters.map(ch => ({ ...ch, topics: ch.topics.map(topic => ({ ...topic, subtopics: topic.subtopics.filter(s =>
    (!text || `${s.name} ${topic.name} ${ch.name}`.toLowerCase().includes(text.toLowerCase())) && (filter === 'all' || filter === 'weak' || s.status === filter) && (!weak || s.weak)
  ).sort((a: SubtopicNode, b: SubtopicNode) => {
    const rank = (status: string) => status === 'in_progress' ? 0 : status === 'not_started' ? 1 : 2;
    return (sort === 'seq' ? a.seq - b.seq : sort === 'not_done' ? rank(a.status) - rank(b.status) : (b.importance ?? -1) - (a.importance ?? -1)) || a.id.localeCompare(b.id);
  }) })).filter(topic => topic.subtopics.length) })).filter(ch => ch.topics.length) ?? [];
  return <div className="space-y-5"><Link className="topic-link" to={demoLink(overviewPath)}>← Papers</Link><h1 className="page-title">{tree ? `${tree.code} — ${tree.name}` : 'Paper detail'}</h1><PageState loading={query.isPending} error={query.error} retry={() => query.refetch()} />
    {nodeId ? <><Link className="topic-link" to={demoLink(backPath)}>← Return</Link><SubtopicDetail key={nodeId} paperId={paperId} nodeId={nodeId} /></> : tree && <>
      <div className="controls"><label>Search <input aria-label="Search" value={text} onChange={e => set({ search: e.target.value })} /></label><label>Status <select aria-label="Status" value={filter} onChange={e => set({ status: e.target.value })}><option value="all">All statuses</option><option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="done">Done</option></select></label><label><input type="checkbox" checked={weak} onChange={e => set({ weak: e.target.checked ? 'true' : '', status: filter === 'weak' ? 'all' : filter })} /> Weak only</label><label>Sort <select aria-label="Sort" value={sort} onChange={e => set({ sort: e.target.value })}><option value="importance">Highest importance</option><option value="seq">Syllabus order</option><option value="not_done">Not done first</option></select></label></div>
      {!chapters.length && <p className="card">{tree.chapters.some(ch => ch.topics.some(t => t.subtopics.length)) ? 'No results match these filters.' : 'No subtopics available.'}</p>}
      {chapters.map(ch => <section className="card space-y-3" key={ch.id}><button className="font-bold" aria-expanded={!collapsed[ch.id]} onClick={() => setCollapsed(previous => ({ ...previous, [ch.id]: !previous[ch.id] }))}>{ch.name} · {ch.completed_subtopics} / {ch.total_subtopics} completed</button>{!collapsed[ch.id] && ch.topics.map(topic => <div className="space-y-2" key={topic.id}><h3 className="font-semibold">{topic.name}</h3>{topic.subtopics.map(s => <div key={s.id}><Link className="topic-link" to={demoLink(`/papers/${tree.paper_id}/${s.id}${search}`)}>{s.name}</Link><p className="text-sm">{s.status.replace(/_/g, ' ')} · Importance {importance(s.importance)}{s.weak ? ' · Weak' : ''}</p></div>)}</div>)}</section>)}
    </>}
  </div>;
}
