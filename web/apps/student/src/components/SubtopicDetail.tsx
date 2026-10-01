import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useBlocker } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest } from '@caf/api-client';
import { getData, mode, jsonOptions, importance } from '../lib/data';
import { isDemoMode } from '../lib/demo';
import { demoUpdate } from '../lib/fixtures';
import { PageState } from './PageState';
import type { SubtopicData, WhyData } from '../lib/contracts';

type Status = 'not_started' | 'in_progress' | 'done';
type Draft = { text: string; saved: string };
const drafts = new Map<string, Draft>();
const saves = new Map<string, { text: string; promise: Promise<unknown> }>();

export function SubtopicDetail({ nodeId }: { paperId: string; nodeId: string }) {
  const cache = useQueryClient();
  const key = `${mode()}:${nodeId}`;
  const [text, setText] = useState(drafts.get(key)?.text ?? '');
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved' | 'failed'>(drafts.get(key)?.text !== drafts.get(key)?.saved ? 'unsaved' : 'saved');
  const [noteError, setNoteError] = useState('');
  const [statusSaved, setStatusSaved] = useState(false);
  const [preview, setPreview] = useState(false);
  const [whyExpanded, setWhyExpanded] = useState(false);
  const mounted = useRef(true);
  const latest = useRef(text);
  const queryKey = ['subtopic', mode(), nodeId];
  const query = useQuery({ queryKey, queryFn: () => getData<SubtopicData>(`/api/v1/subtopics/${encodeURIComponent(nodeId)}`) });
  const why = useQuery({ queryKey: ['why', mode(), nodeId], queryFn: () => getData<WhyData>(`/api/v1/why/subtopic/${encodeURIComponent(nodeId)}`), enabled: whyExpanded });
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (query.data && !drafts.has(key)) {
      const value = query.data.notes ?? '';
      drafts.set(key, { text: value, saved: value });
      latest.current = value; setText(value); setSaveStatus('saved');
    }
  }, [query.data, key]);
  const draft = drafts.get(key);
  const dirty = draft !== undefined && text !== draft.saved;
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state === 'blocked') {
      if (window.confirm('You have unsaved notes. Leave this page?')) blocker.proceed(); else blocker.reset();
    }
  }, [blocker]);
  useEffect(() => {
    if (!dirty) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', unload);
    return () => { window.removeEventListener('beforeunload', unload); };
  }, [dirty]);
  const save = async () => {
    const snapshot = latest.current;
    setSaveStatus('saving'); setNoteError('');
    const previous = saves.get(key)?.promise ?? Promise.resolve();
    const pending = previous.catch(() => undefined).then(async () => {
      if (isDemoMode()) demoUpdate(nodeId, { notes: snapshot });
      else await apiRequest(`/api/v1/subtopics/${encodeURIComponent(nodeId)}/notes`, jsonOptions('PUT', { notes: snapshot }));
      const draft = drafts.get(key);
      if (draft) drafts.set(key, { ...draft, saved: snapshot });
      if (mounted.current) {
        const queuedText = saves.get(key)?.text;
        setSaveStatus(latest.current === snapshot ? 'saved' : queuedText === latest.current ? 'saving' : 'unsaved');
      }
      await cache.invalidateQueries();
    });
    saves.set(key, { text: snapshot, promise: pending });
    try { await pending; }
    catch (error) { if (mounted.current) { setSaveStatus('failed'); setNoteError(error instanceof Error ? error.message : 'Save failed'); } }
    finally { if (saves.get(key)?.promise === pending) saves.delete(key); }
  };
  useEffect(() => {
    if (saveStatus !== 'unsaved') return;
    const timer = window.setTimeout(() => { void save(); }, 1000);
    return () => window.clearTimeout(timer);
  }, [text, saveStatus]);
  const progress = useMutation({
    mutationFn: async (status: Status) => {
      if (isDemoMode()) { demoUpdate(nodeId, { status }); return; }
      await apiRequest(`/api/v1/subtopics/${encodeURIComponent(nodeId)}/progress`, jsonOptions('PUT', { status }));
    },
    onMutate: async status => {
      setStatusSaved(false);
      await cache.cancelQueries({ queryKey });
      const previous = cache.getQueryData<SubtopicData>(queryKey);
      if (previous) cache.setQueryData(queryKey, { ...previous, status });
      return previous;
    },
    onError: (_error, _status, previous) => { if (previous) cache.setQueryData(queryKey, previous); },
    onSuccess: async () => { setStatusSaved(true); await cache.invalidateQueries(); },
  });
  const data = query.data;
  const breakdown = why.data?.importance_breakdown;
  return <div className="space-y-4"><PageState loading={query.isPending} error={query.error} retry={() => query.refetch()} />{data && <>
    <section className="card space-y-3"><h2 className="text-xl font-bold">{data.name}</h2><p>{data.paper?.name} / {data.chapter?.name} / {data.topic?.name}</p><p>Importance: {importance(data.score.importance)}</p><div className="controls"><label>Progress <select aria-label="Progress" disabled={progress.isPending} value={data.status} onChange={e => progress.mutate(e.target.value as Status)}><option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="done">Done</option></select></label>{progress.isPending && <span role="status">Saving progress…</span>}{statusSaved && <span role="status">Progress saved.</span>}</div>{progress.error && <p role="alert" className="text-red-700">Progress was not saved: {progress.error.message}</p>}</section>
    <section className="card space-y-3"><h3 className="font-bold">Notes</h3><button aria-pressed={preview} onClick={() => setPreview(!preview)}>{preview ? 'Edit notes' : 'Preview notes'}</button>{preview ? <div className="prose dark:prose-invert whitespace-pre-wrap"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text || 'No notes yet.'}</ReactMarkdown></div> : <textarea aria-label="Notes" className="field w-full min-h-48" value={text} onChange={e => { const next = e.target.value; latest.current = next; setText(next); const draft = drafts.get(key); drafts.set(key, { text: next, saved: draft?.saved ?? data.notes ?? '' }); setSaveStatus('unsaved'); }} />}<p role="status">{saveStatus === 'failed' ? `Failed to save: ${noteError}` : saveStatus === 'unsaved' ? 'Unsaved changes' : saveStatus === 'saving' ? 'Saving…' : 'Saved'}</p><button className="action" disabled={!dirty || saveStatus === 'saving'} onClick={() => { void save(); }}>Save notes</button></section>
    <section className="card space-y-3"><button className="font-bold" aria-expanded={whyExpanded} onClick={() => setWhyExpanded(!whyExpanded)}>Why this importance?</button>{whyExpanded && <><PageState loading={why.isPending} error={why.error} retry={() => why.refetch()} />{why.data && <><p>Run {why.data.score_run?.id ?? 'Unavailable'} · {why.data.score_run?.version ?? 'Unavailable'} · Target {why.data.score_run?.target_attempt_id ?? 'Unavailable'} · {why.data.score_run?.computed_at ?? 'Timestamp unavailable'}</p>{why.data.explanation_status !== 'available' ? <p>{why.data.explanation_status === 'historical_configuration_unavailable' ? 'Historical configuration unavailable. Recorded importance is preserved; derived contributions are unavailable.' : 'Score explanation unavailable.'}</p> : breakdown?.exam && breakdown.practice && breakdown.weightage_prior && breakdown.weights && <><table className="w-full text-left text-sm"><caption>Normalized signals (0–100)</caption><thead><tr><th>Signal</th><th>Normalized</th><th>Weight</th><th>Weighted contribution</th></tr></thead><tbody><tr><td>Exam E</td><td>{breakdown.exam.normalized_E_pct}</td><td>{breakdown.weights.exam}</td><td>{breakdown.exam.weighted_contribution_pct}</td></tr><tr><td>Practice P</td><td>{breakdown.practice.normalized_P_pct}</td><td>{breakdown.weights.practice}</td><td>{breakdown.practice.weighted_contribution_pct}</td></tr><tr><td>Weightage W</td><td>{breakdown.weightage_prior.normalized_W_pct}</td><td>{breakdown.weights.prior}</td><td>{breakdown.weightage_prior.weighted_contribution_pct}</td></tr></tbody></table><p>Raw exam signal: {breakdown.exam.score_E} (decayed marks); raw practice signal: {breakdown.practice.score_P} (decayed marks); raw weightage prior: {breakdown.weightage_prior.weight_prior_W} (allocated weightage marks per applicable subtopic).</p></>}</>}</>}</section>
    <section className="card space-y-3"><h3 className="font-bold">Appearances</h3>{data.appearances.length ? data.appearances.map(a => <div key={a.id}><p>{a.display_label} · {a.attempt_id} · {a.marks == null ? 'Marks unavailable' : `${a.marks} marks`} · {a.signal_class}</p>{a.gist && <p className="whitespace-pre-wrap">{a.gist}</p>}{a.official_url && <a className="topic-link" href={a.official_url}>Official source</a>}</div>) : <p>No published appearances.</p>}</section>
  </>}</div>;
}
