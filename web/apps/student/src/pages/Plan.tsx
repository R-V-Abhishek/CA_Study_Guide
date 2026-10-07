import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { PageState } from '../components/PageState';
import { getData, mode, usePapers, importance } from '../lib/data';
import { useUrlState } from '../lib/url';
import { demoLink } from '../lib/demo';
import type { PlanData } from '../lib/contracts';
import { StudyContext, type StudyContextFields } from '../components/StudyContext';
export function Plan() {
  const { params, set, search } = useUrlState();
  const hoursText = params.get('hours');
  const hours = hoursText == null ? null : Number(hoursText);
  const group = params.get('group') ?? 'all';
  const paper = params.get('paper') ?? 'all';
  const destination = (paperId: string, nodeId: string) => demoLink(`/papers/${paperId}/${nodeId}?return=${encodeURIComponent(`/plan${search}`)}`);
  const valid = (hours == null || (Number.isFinite(hours) && hours > 0)) && ['all', '1', '2'].includes(group);
  const papersQuery = usePapers();
  const papers = papersQuery.data ?? [];
  const options = papers.filter(p => group === 'all' || String(p.group_no) === group);
  useEffect(() => {
    if (papersQuery.data && paper !== 'all' && !options.some(p => p.id === paper || p.code === paper)) set({ paper: 'all' });
  }, [papersQuery.data, group, paper]);
  const query = useQuery({
    queryKey: ['study-plan', mode(), hours, group, paper], enabled: valid,
    queryFn: () => {
      const query = new URLSearchParams();
      if (hours != null) query.set('hours', String(hours));
      if (group !== 'all') query.set('group', group);
      if (paper !== 'all') query.set('paper', paper);
      return getData<PlanData>(`/api/v1/plan?${query}`);
    },
  });
  const guidance = query.data as (PlanData & StudyContextFields & { basis?: string; allocated_minutes?: number; unused_minutes?: number; score_run_id?: number | null }) | undefined;
  return <div className="space-y-5"><h1 className="page-title">Weekly Study Plan</h1><p>Study allocation follows your selected syllabus and recorded personal progress. Historical importance is a relative study signal.</p>
    <div className="controls">
      <label>Hours per week <input aria-label="Hours per week" type="number" min="0.01" step="any" value={hoursText ?? query.data?.hours_per_week ?? ''} onChange={e => set({ hours: e.target.value })} /></label>
      <label>Group <select aria-label="Group" value={group} onChange={e => { const next = e.target.value; const compatible = next === 'all' || papers.some(p => (p.id === paper || p.code === paper) && String(p.group_no) === next); set({ group: next, paper: compatible ? paper : 'all' }); }}><option value="all">All groups</option><option value="1">Group 1</option><option value="2">Group 2</option></select></label>
      <label>Paper <select aria-label="Paper" value={paper} onChange={e => set({ paper: e.target.value })}><option value="all">All papers</option>{options.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></label>
      <button className="action" disabled={!valid || query.isFetching} onClick={() => query.refetch()}>Refresh plan</button>
    </div>
    {!valid && <p role="alert">Enter finite positive hours and a supported group (1 or 2).</p>}
    <PageState loading={valid && query.isPending} error={query.error ?? papersQuery.error} retry={() => { query.refetch(); papersQuery.refetch(); }} />
    {query.data && <><StudyContext data={guidance ?? {}} /><p>Plan basis: {guidance?.basis === 'syllabus' ? 'Syllabus-based plan — in-progress items, then reviewed textbook order' : guidance?.basis === 'scored' ? 'Historical importance and personal progress' : 'Historical basis unavailable'}</p><p>{query.data.hours_per_week} hours per week · {query.data.minutes_per_subtopic} minutes per subtopic · {query.data.total_allocated} allocated</p>{guidance?.allocated_minutes != null && <p>{guidance.allocated_minutes} minutes allocated · {guidance.unused_minutes ?? 0} minutes unused · Snapshot {guidance.score_run_id ?? 'Unavailable'}</p>}
      {query.data.score_unavailable_reason && <p>{query.data.score_unavailable_reason}</p>}
      {query.data.items.length === 0 ? <p className="card">No topics allocated for this budget and selection.</p> : <ol className="space-y-3">{query.data.items.map((item, index) => <li className="card" key={item.node_id}><Link className="topic-link font-semibold" to={destination(item.paper_id, item.node_id)}>{index + 1}. {item.node_name}</Link><p>{item.paper_code} · {query.data.minutes_per_subtopic} minutes · Importance {importance(item.importance)}</p><p>{item.reason}</p></li>)}</ol>}
    </>}
  </div>;
}
