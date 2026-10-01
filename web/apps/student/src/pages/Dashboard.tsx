import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getData, mode, formatPct, importance } from '../lib/data';
import { demoLink } from '../lib/demo';
import { PageState } from '../components/PageState';
import type { DashboardData } from '../lib/contracts';
export function Dashboard() {
  const query = useQuery({ queryKey: ['dashboard', mode()], queryFn: () => getData<DashboardData>('/api/v1/dashboard') });
  const data = query.data;
  return <div className="space-y-5"><h1 className="page-title">Dashboard</h1><PageState loading={query.isPending} error={query.error} retry={() => query.refetch()} />{data && <>
    <p>Target attempt: {data.target_attempt}</p>
    <div className="grid md:grid-cols-3 gap-4"><div className="card">{data.done_subtopics} / {data.total_subtopics} topics completed<br />{formatPct(data.overall_progress_pct)} completion</div><div className="card">Group 1: {formatPct(data.group1_progress_pct)}<br />Group 2: {formatPct(data.group2_progress_pct)}</div><div className="card">{data.revision_due_count} revisions due<br /><Link className="topic-link" to={demoLink('/revision')}>Open revision queue</Link></div></div>
    <section className="card space-y-3"><h2 className="font-bold">Plan preview</h2>{data.plan_preview.length ? data.plan_preview.map(item => <div key={item.node_id}><Link className="topic-link" to={demoLink(`/papers/${item.paper_id}/${item.node_id}`)}>{item.node_name}</Link><p>{item.paper_code} · Importance {importance(item.importance)} · {item.reason}</p></div>) : <p>No topics allocated.</p>}<Link className="topic-link" to={demoLink('/plan')}>View weekly study plan</Link></section>
    <section className="card space-y-3"><h2 className="font-bold">Weak topics</h2>{data.weak_subtopics.length ? data.weak_subtopics.map(item => <Link className="topic-link block" key={item.node_id} to={demoLink(`/papers/${item.paper_id}/${item.node_id}`)}>{item.node_name} · {item.paper_code}</Link>) : <p>No weak topics identified.</p>}</section>
    <section className="card space-y-3"><h2 className="font-bold">Recent activity</h2>{data.recent_activity.length ? data.recent_activity.map((item, index) => <p key={`${item.node_id}-${index}`}>{item.node_name} · {item.to_status} · {item.at}</p>) : <p>No recent activity.</p>}</section>
  </>}</div>;
}
