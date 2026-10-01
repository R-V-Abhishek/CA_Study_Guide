import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@caf/api-client';
import { getData, mode, jsonOptions, importance } from '../lib/data';
import { demoLink, isDemoMode } from '../lib/demo';
import { demoRevise } from '../lib/fixtures';
import { PageState } from '../components/PageState';
import type { RevisionData, SubtopicData } from '../lib/contracts';
export function Revision() {
  const cache = useQueryClient();
  const [accepted, setAccepted] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const query = useQuery({ queryKey: ['revision-due', mode()], queryFn: () => getData<RevisionData>('/api/v1/revision/due') });
  const current = query.data?.items.find(item => !accepted.includes(item.node_id));
  const detail = useQuery({ queryKey: ['subtopic', mode(), current?.node_id], queryFn: () => getData<SubtopicData>(`/api/v1/subtopics/${encodeURIComponent(current!.node_id)}`), enabled: !!current });
  const mutation = useMutation({ mutationFn: async ({ id, outcome }: { id: string; outcome: 'ok' | 'shaky' }) => {
    if (isDemoMode()) demoRevise(id);
    else await apiRequest(`/api/v1/subtopics/${encodeURIComponent(id)}/revisions`, jsonOptions('POST', { outcome }));
    return id;
  }, onSuccess: async id => { setAccepted(previous => [...previous, id]); setSaved(true); await cache.invalidateQueries(); } });
  return <div className="space-y-5"><h1 className="page-title">Revision</h1><PageState loading={query.isPending} error={query.error} retry={() => query.refetch()} />{saved && <p role="status">Revision saved.</p>}{mutation.error && <p role="alert" className="card text-red-700">Revision was not saved: {mutation.error.message}</p>}
    {query.data && (current ? <section className="card space-y-4"><h2 className="font-bold text-xl">{current.node_name}</h2><p>{current.paper_code} · {detail.data?.chapter?.name ?? ''} · Importance {importance(current.importance)}</p><p className="whitespace-pre-wrap">{detail.data?.notes ?? 'Notes unavailable.'}</p><Link className="topic-link" to={demoLink(`/papers/${current.paper_id}/${current.node_id}`)}>Open topic</Link><div className="controls"><button className="action" disabled={mutation.isPending} onClick={() => { setSaved(false); mutation.mutate({ id: current.node_id, outcome: 'ok' }); }}>Remembered</button><button className="action" disabled={mutation.isPending} onClick={() => { setSaved(false); mutation.mutate({ id: current.node_id, outcome: 'shaky' }); }}>Needs another revision</button>{mutation.isPending && <span role="status">Saving revision…</span>}</div></section> : <p className="card">{accepted.length ? 'Revision queue complete.' : 'No revisions due.'}</p>)}
  </div>;
}
