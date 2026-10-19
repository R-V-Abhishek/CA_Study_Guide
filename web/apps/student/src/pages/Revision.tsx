import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest, authGeneration } from '@caf/api-client';
import { getData, mode, jsonOptions } from '../lib/data';
import { demoLink, isDemoMode } from '../lib/demo';
import { demoRevise } from '../lib/fixtures';
import { PageState } from '../components/PageState';
import { useUrlState } from '../lib/url';
import type { RevisionData, SubtopicData } from '../lib/contracts';
export function Revision() {
  const cache = useQueryClient();
  const { params, set } = useUrlState();
  const [accepted, setAccepted] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [reveal, setReveal] = useState(false);
  const context = mode();
  const generation = authGeneration();
  useEffect(() => { setAccepted([]); setSaved(false); setReveal(false); }, [context]);
  const query = useQuery({ queryKey: ['revision-due', context], queryFn: () => getData<RevisionData>('/api/v1/revision/due') });
  const items = query.data?.items.filter(item => !accepted.includes(item.node_id)) ?? [];
  const current = items.find(item => item.node_id === params.get('node')) ?? items[0];
  const index = items.findIndex(item => item.node_id === current?.node_id);
  useEffect(() => { setReveal(false); }, [current?.node_id]);
  const detail = useQuery({ queryKey: ['subtopic', mode(), current?.node_id], queryFn: () => getData<SubtopicData>(`/api/v1/subtopics/${encodeURIComponent(current!.node_id)}`), enabled: !!current });
  const mutation = useMutation({ mutationFn: async ({ id, outcome }: { id: string; outcome: 'ok' | 'shaky' }) => { if (isDemoMode()) demoRevise(id); else await apiRequest(`/api/v1/subtopics/${encodeURIComponent(id)}/revisions`, jsonOptions('POST', { outcome })); return id; }, onSuccess: async id => { if (generation !== authGeneration()) return; setAccepted(previous => [...previous,id]); setSaved(true); set({ node: '' }); await cache.invalidateQueries(); } });
  return <div className="space-y-5"><h1 className="page-title">Revision</h1><p>Recall a due topic, then deliberately record how the revision went.</p><PageState loading={query.isPending} refreshing={query.isFetching && Boolean(query.data)} error={query.error} retry={() => query.refetch()} />{saved && <p role="status">Revision saved.</p>}{mutation.error && <p role="alert" className="card">Revision was not saved: {mutation.error.message}. The current topic is retained.</p>}{query.data && <><p className="study-meta">{items.length} topics due</p>{current ? <div className="revision-columns"><nav className="card revision-queue" aria-label="Revision queue">{[{ title: 'Overdue', items: items.filter(item => item.overdue_days > 0) }, { title: 'Due today', items: items.filter(item => item.overdue_days === 0) }].filter(group => group.items.length > 0).map(group => <section key={group.title}><h2 className="font-semibold">{group.title}</h2>{group.items.map(item => <button key={item.node_id} aria-current={current.node_id === item.node_id} disabled={mutation.isPending} onClick={() => set({ node: item.node_id })}><span className="font-semibold">{item.node_name}</span><span className="study-meta block">{item.paper_code} · Due {item.due_date}{item.overdue_days > 0 ? ` · ${item.overdue_days} days overdue` : ''}</span></button>)}</section>)}</nav><section className="card space-y-4"><h2 className="text-xl font-semibold">{current.node_name}</h2><p className="study-meta">{[current.paper_code,detail.data?.chapter?.name,detail.data?.topic?.name].filter(Boolean).join(' / ')}</p><p>Due {current.due_date}{current.overdue_days > 0 ? ` · ${current.overdue_days} days overdue` : ''}</p><Link className="topic-link" to={demoLink(`/syllabus?${new URLSearchParams({ paper: current.paper_id, node: current.node_id })}`)}>Open topic and relevant questions</Link><button aria-expanded={reveal} onClick={() => setReveal(!reveal)}>{reveal ? 'Hide my notes' : 'Reveal my notes'}</button>{reveal && <><PageState loading={detail.isPending} error={detail.error} retry={() => detail.refetch()} />{detail.data && <p className="whitespace-pre-wrap">{detail.data.notes || 'No personal notes for this topic.'}</p>}</>}<div className="controls"><button className="action" disabled={mutation.isPending} onClick={() => { setSaved(false); mutation.mutate({ id: current.node_id, outcome: 'ok' }); }}>Recall was okay</button><button disabled={mutation.isPending} onClick={() => { setSaved(false); mutation.mutate({ id: current.node_id, outcome: 'shaky' }); }}>Needs another revision</button>{mutation.isPending && <span role="status">Saving revision…</span>}</div><div className="controls"><button disabled={index <= 0 || mutation.isPending} onClick={() => set({ node: items[index - 1].node_id })}>Previous topic</button><button disabled={index >= items.length - 1 || mutation.isPending} onClick={() => set({ node: items[index + 1].node_id })}>Next topic</button></div><p className="study-meta">Previous and next only navigate. They do not record an outcome.</p></section></div> : <p className="card">{accepted.length ? 'Revision queue complete.' : 'Nothing is due for revision.'}</p>}</>}</div>;
}
