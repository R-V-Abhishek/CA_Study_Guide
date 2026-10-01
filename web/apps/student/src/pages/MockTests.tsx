import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@caf/api-client';
import { getData, mode, jsonOptions, usePapers, formatPct } from '../lib/data';
import { isDemoMode } from '../lib/demo';
import { demoCreateMock, demoDeleteMock } from '../lib/fixtures';
import { useUrlState } from '../lib/url';
import { PageState } from '../components/PageState';
import type { MockTest } from '../lib/contracts';
export function MockTests() {
  const { params, set } = useUrlState();
  const selectedPaper = params.get('paper') ?? 'all';
  const cache = useQueryClient();
  const papers = usePapers();
  const [open, setOpen] = useState(false);
  const [paper, setPaper] = useState('');
  const [label, setLabel] = useState('');
  const [score, setScore] = useState('');
  const [maximum, setMaximum] = useState('100');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  const [feedback, setFeedback] = useState('');
  const query = useQuery({ queryKey: ['mock-tests', mode(), selectedPaper], queryFn: () => getData<MockTest[]>(`/api/v1/mock-tests${selectedPaper === 'all' ? '' : `?paper=${encodeURIComponent(selectedPaper)}`}`) });
  const create = useMutation({ mutationFn: async () => {
    const body = { paper_id: paper, label, score: Number(score), max_score: Number(maximum), taken_on: date, notes };
    if (isDemoMode()) demoCreateMock(body); else await apiRequest('/api/v1/mock-tests', jsonOptions('POST', body));
  }, onSuccess: async () => { setOpen(false); setFeedback('Mock test saved.'); await cache.invalidateQueries(); } });
  const remove = useMutation({ mutationFn: async (id: number) => {
    if (isDemoMode()) demoDeleteMock(id); else await apiRequest(`/api/v1/mock-tests/${id}`, { method: 'DELETE' });
  }, onSuccess: async () => { setFeedback('Mock test deleted.'); await cache.invalidateQueries(); } });
  const valid = paper !== '' && score !== '' && Number.isFinite(Number(score)) && Number(score) >= 0 && Number.isFinite(Number(maximum)) && Number(maximum) > 0 && Number(score) <= Number(maximum) && date !== '';
  return <div className="space-y-5"><h1 className="page-title">Mock Tests</h1><div className="controls"><label>Paper <select aria-label="Paper filter" value={selectedPaper} onChange={e => set({ paper: e.target.value })}><option value="all">All papers</option>{papers.data?.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></label><button className="action" onClick={() => { setOpen(true); setFeedback(''); setPaper(selectedPaper === 'all' ? papers.data?.[0]?.id ?? '' : selectedPaper); }}>Record mock test</button></div>
    <PageState loading={query.isPending || papers.isPending} error={query.error ?? papers.error} retry={() => { query.refetch(); papers.refetch(); }} />{feedback && <p role="status">{feedback}</p>}{remove.error && <p role="alert">Deletion failed: {remove.error.message}</p>}
    {open && <form className="card space-y-3" onSubmit={e => { e.preventDefault(); setFeedback(''); create.mutate(); }}><h2 className="font-bold">Record mock test</h2><div className="controls"><label>Paper <select aria-label="Mock paper" value={paper} onChange={e => setPaper(e.target.value)}>{papers.data?.map(p => <option key={p.id} value={p.id}>{p.code}</option>)}</select></label><label>Label <input aria-label="Label" value={label} onChange={e => setLabel(e.target.value)} /></label><label>Score <input aria-label="Score" type="number" step="any" min="0" value={score} onChange={e => setScore(e.target.value)} /></label><label>Maximum score <input aria-label="Maximum score" type="number" step="any" min="0.01" value={maximum} onChange={e => setMaximum(e.target.value)} /></label><label>Date <input aria-label="Date" type="date" value={date} onChange={e => setDate(e.target.value)} /></label></div><textarea aria-label="Mock notes" className="field w-full" value={notes} onChange={e => setNotes(e.target.value)} />{create.error && <p role="alert">Creation failed: {create.error.message}</p>}<div className="controls"><button className="action" disabled={!valid || create.isPending}>Save mock test</button><button type="button" onClick={() => setOpen(false)}>Cancel</button></div></form>}
    {query.data && (query.data.length ? <div className="space-y-3">{[...query.data].sort((a, b) => b.taken_on.localeCompare(a.taken_on) || a.id - b.id).map(test => <section className="card space-y-2" key={test.id}><h2 className="font-bold">{test.label ?? 'Mock test'} · {test.paper_code}</h2><p>{test.score} / {test.max_score} · {formatPct(test.score_pct)} · {test.taken_on}</p>{test.notes && <p className="whitespace-pre-wrap">{test.notes}</p>}<button disabled={remove.isPending} onClick={() => { setFeedback(''); remove.mutate(test.id); }}>Delete mock test</button></section>)}</div> : <p className="card">{selectedPaper === 'all' ? 'No mock tests recorded.' : 'No mock tests match this paper.'}</p>)}
  </div>;
}
