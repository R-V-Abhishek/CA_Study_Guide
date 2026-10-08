import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest, authGeneration } from '@caf/api-client';
import { getData, mode, jsonOptions, usePapers, formatPct } from '../lib/data';
import { isDemoMode } from '../lib/demo';
import { demoCreateMock, demoDeleteMock } from '../lib/fixtures';
import { useUrlState } from '../lib/url';
import { PageState } from '../components/PageState';
import { Dialog } from '../../../../packages/workspace/Dialog';
import type { MockTest } from '../lib/contracts';
export function MockTests() {
  const { params, set } = useUrlState();
  const selectedPaper = params.get('paper') ?? 'all';
  const cache = useQueryClient();
  const papers = usePapers();
  const [open,setOpen] = useState(false);
  const [deleting,setDeleting] = useState<MockTest | null>(null);
  const [paper,setPaper] = useState('');
  const [label,setLabel] = useState('');
  const [score,setScore] = useState('');
  const [maximum,setMaximum] = useState('100');
  const [date,setDate] = useState(new Date().toISOString().slice(0,10));
  const [notes,setNotes] = useState('');
  const [feedback,setFeedback] = useState('');
  const generation = authGeneration();
  const query = useQuery({ queryKey:['mock-tests',mode(),selectedPaper],queryFn:() => getData<MockTest[]>(`/api/v1/mock-tests${selectedPaper === 'all' ? '' : `?paper=${encodeURIComponent(selectedPaper)}`}`) });
  const create = useMutation({ mutationFn:async () => { const body={ paper_id:paper,label,score:Number(score),max_score:Number(maximum),taken_on:date,notes }; if (isDemoMode()) demoCreateMock(body); else await apiRequest('/api/v1/mock-tests',jsonOptions('POST',body)); },onSuccess:async () => { if (generation !== authGeneration()) return; setOpen(false);setFeedback('Mock result saved.');await cache.invalidateQueries(); } });
  const remove = useMutation({ mutationFn:async (id:number) => { if (isDemoMode()) demoDeleteMock(id);else await apiRequest(`/api/v1/mock-tests/${id}`,{ method:'DELETE' }); },onSuccess:async () => { if (generation !== authGeneration()) return; setDeleting(null);setFeedback('Mock result deleted.');await cache.invalidateQueries(); } });
  const valid=!!papers.data?.some(item => item.id === paper) && score !== '' && Number.isFinite(Number(score)) && Number(score) >= 0 && Number.isFinite(Number(maximum)) && Number(maximum) > 0 && Number(score) <= Number(maximum) && date !== '';
  const records=[...(query.data ?? [])].sort((a,b) => b.taken_on.localeCompare(a.taken_on) || a.id - b.id);
  const trend=selectedPaper !== 'all' && records.length >= 2 && new Set(records.map(item => item.max_score)).size === 1 ? [...records].reverse() : [];
  return <div className="space-y-5"><h1 className="page-title">Mock results</h1><p>Record actual practice results for each paper and compare compatible records.</p><div className="controls"><label>Paper <select aria-label="Paper filter" value={selectedPaper} onChange={event => set({ paper:event.target.value })}><option value="all">All papers</option>{papers.data?.map(item => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label><button className="action" disabled={!papers.data?.length} onClick={() => { setOpen(true);setFeedback('');create.reset();setPaper(papers.data?.some(item => item.id === selectedPaper) ? selectedPaper : papers.data?.[0]?.id ?? ''); }}>Add result</button></div><PageState loading={query.isPending || papers.isPending} refreshing={query.isFetching && Boolean(query.data)} error={query.error ?? papers.error} retry={() => { query.refetch();papers.refetch(); }} />{feedback && <p role="status">{feedback}</p>}{trend.length > 0 && <section className="card space-y-2"><h2 className="font-semibold">Paper trend</h2>{trend.map(test => <div key={test.id}><p className="study-meta">{test.taken_on} · {formatPct(test.score_pct)}</p><progress className="study-bar" max={test.max_score} value={test.score} aria-label={`Result ${test.taken_on}: ${test.score} of ${test.max_score}`} /></div>)}</section>}{query.data && (records.length ? <div className="card study-table-wrap"><table className="study-table"><thead><tr><th>Date</th><th>Paper</th><th>Marks scored</th><th>Maximum marks</th><th>Percentage</th><th>Notes</th><th>Action</th></tr></thead><tbody>{records.map(test => <tr key={test.id}><td>{test.taken_on}</td><td>{test.paper_code}{test.label && <span className="study-meta block">{test.label}</span>}</td><td>{test.score}</td><td>{test.max_score}</td><td>{formatPct(test.score_pct)}</td><td className="whitespace-pre-wrap">{test.notes || '—'}</td><td><button disabled={remove.isPending} onClick={() => { remove.reset();setDeleting(test); }}>Delete result</button></td></tr>)}</tbody></table></div> : <p className="card">{selectedPaper === 'all' ? 'No mock results recorded.' : 'No mock results match this paper.'}</p>)}
    <Dialog open={open} title="Add mock result" onClose={() => { if (!create.isPending) setOpen(false); }}><form className="space-y-3" onSubmit={event => { event.preventDefault();if (valid) create.mutate(); }}><div className="controls"><label>Paper <select aria-label="Mock paper" value={paper} onChange={event => setPaper(event.target.value)}>{papers.data?.map(item => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label><label>Label <input aria-label="Label" value={label} onChange={event => setLabel(event.target.value)} /></label><label>Marks scored <input aria-label="Marks scored" type="number" required step="any" min="0" max={maximum} value={score} onChange={event => setScore(event.target.value)} /></label><label>Maximum marks <input aria-label="Maximum marks" required type="number" step="any" min="0.01" value={maximum} onChange={event => setMaximum(event.target.value)} /></label><label>Date <input aria-label="Date" required type="date" value={date} onChange={event => setDate(event.target.value)} /></label></div><label className="block">Notes <textarea aria-label="Mock notes" className="field w-full" value={notes} onChange={event => setNotes(event.target.value)} /></label>{!valid && <p className="study-meta">Choose a paper, date and a score from zero to the positive maximum.</p>}{create.error && <p role="alert">Save failed: {create.error.message}. Your entries are retained.</p>}<button className="action" disabled={!valid || create.isPending}>{create.isPending ? 'Saving…' : 'Save result'}</button></form></Dialog>
    <Dialog open={Boolean(deleting)} title="Delete mock result" onClose={() => { if (!remove.isPending) setDeleting(null); }}><p>Delete {deleting?.label || 'mock result'} for {deleting?.paper_code}, taken {deleting?.taken_on}, scoring {deleting?.score} / {deleting?.max_score}?</p><div className="controls"><button disabled={remove.isPending} onClick={() => setDeleting(null)}>Keep result</button><button className="destructive" disabled={remove.isPending} onClick={() => { if (deleting) remove.mutate(deleting.id); }}>{remove.isPending ? 'Deleting…' : 'Confirm delete'}</button></div>{remove.error && <p role="alert">Deletion failed: {remove.error.message}</p>}</Dialog>
  </div>;
}
