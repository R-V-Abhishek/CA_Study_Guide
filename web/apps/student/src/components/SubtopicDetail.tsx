import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Link, useBlocker, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiRequest, accountKey, authGeneration, onIdentityReset, type QuestionPage } from '@caf/api-client';
import { taxonomyApi, type TextbookNode } from '@caf/api-client/src/taxonomy';
import { getData, mode, jsonOptions } from '../lib/data';
import { isDemoMode, demoLink } from '../lib/demo';
import { demoUpdate } from '../lib/fixtures';
import { PageState } from './PageState';
import type { SubtopicData, WhyData } from '../lib/contracts';
import { StudyContext, type StudyContextFields } from './StudyContext';
import { ScoreExplanation } from './ScoreExplanation';
import { useUrlState } from '../lib/url';
import { rememberDestination, preserveOrigin, restoreOrigin } from '../lib/navigation';
import { Dialog } from '../../../../packages/workspace/Dialog';
import { TextbookSources } from './TextbookExplorer';

type Status = 'not_started' | 'in_progress' | 'done';
type Draft = { text: string; saved: string };
const drafts = new Map<string, Draft>();
const timers = new Set<number>();
onIdentityReset(() => { timers.forEach(timer => window.clearTimeout(timer)); timers.clear(); drafts.clear(); saves.clear(); });
const saves = new Map<string, { text: string; promise: Promise<unknown> }>();

export function SubtopicDetail({ nodeId }: { paperId: string; nodeId: string }) {
  const cache = useQueryClient();
  const location = useLocation();
  const { params, set } = useUrlState();
  const tab = params.get('tab') ?? 'questions';
  const pageValue = Number(params.get('question_page') ?? '1');
  const questionPage = Number.isSafeInteger(pageValue) && pageValue > 0 ? pageValue : 1;
  const generation = authGeneration();
  const key = `${isDemoMode() ? 'demo' : `live:${accountKey()}`}:${nodeId}`;
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
  const why = useQuery({ queryKey: ['why', mode(), nodeId], queryFn: () => getData<WhyData>(`/api/v1/why/subtopic/${encodeURIComponent(nodeId)}`), enabled: whyExpanded || tab === 'importance' });
  const published = useQuery({ queryKey: ['topic-questions', mode(), nodeId, questionPage], enabled: tab === 'questions', queryFn: () => getData<QuestionPage>(`/api/v1/questions?subtopic_id=${encodeURIComponent(nodeId)}&page_size=20&page=${questionPage}`) });
  const versions = useQuery({ queryKey: ['textbook-versions', accountKey()], enabled: !isDemoMode() && query.data?.context?.taxonomy_version_id != null, queryFn: taxonomyApi.versions });
  const version = versions.data?.find(item => item.taxonomy_version_id === query.data?.context?.taxonomy_version_id)?.version_id;
  const sources = useQuery({ queryKey: ['textbook-tree', accountKey(), version], enabled: Boolean(version), queryFn: () => taxonomyApi.tree(version!) });
  function locate(items: TextbookNode[]): TextbookNode | undefined { for (const item of items) { if (item.id === nodeId) return item; const child = locate(item.children); if (child) return child; } }
  const sourceNode = locate(sources.data ?? []);
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
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && (currentLocation.pathname !== nextLocation.pathname || new URLSearchParams(currentLocation.search).get('node') !== new URLSearchParams(nextLocation.search).get('node')));
  useEffect(() => {
    if (!dirty) return;
    const beforeLogout = (event: Event) => { if (!window.confirm('You have unsaved notes. Sign out and discard them?')) event.preventDefault(); };
    window.addEventListener('caf-before-logout', beforeLogout);
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', unload);
    return () => { window.removeEventListener('beforeunload', unload); window.removeEventListener('caf-before-logout', beforeLogout); };
  }, [dirty]);
  const save = async () => {
    const snapshot = latest.current;
    setSaveStatus('saving'); setNoteError('');
    const previous = saves.get(key)?.promise ?? Promise.resolve();
    const pending = previous.catch(() => undefined).then(async () => {
      if (generation !== authGeneration()) return;
      if (isDemoMode()) demoUpdate(nodeId, { notes: snapshot });
      else await apiRequest(`/api/v1/subtopics/${encodeURIComponent(nodeId)}/notes`, jsonOptions('PUT', { notes: snapshot }));
      if (generation !== authGeneration()) return;
      const draft = drafts.get(key);
      if (draft) drafts.set(key, { ...draft, saved: snapshot });
      if (mounted.current) {
        const queuedText = saves.get(key)?.text;
        setSaveStatus(latest.current === snapshot ? 'saved' : queuedText === latest.current ? 'saving' : 'unsaved');
      }
      await cache.invalidateQueries();
    });
    saves.set(key, { text: snapshot, promise: pending });
    try { await pending; return generation === authGeneration() && drafts.get(key)?.saved === latest.current; }
    catch (error) { if (mounted.current) { setSaveStatus('failed'); setNoteError(error instanceof Error ? error.message : 'Save failed'); } return false; }
    finally { if (saves.get(key)?.promise === pending) saves.delete(key); }
  };
  useEffect(() => {
    if (saveStatus !== 'unsaved') return;
    const timer = window.setTimeout(() => { void save(); }, 1000);
    timers.add(timer);
    return () => { window.clearTimeout(timer); timers.delete(timer); };
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
    onError: (_error, _status, previous) => { if (previous && generation === authGeneration()) cache.setQueryData(queryKey, previous); },
    onSuccess: async () => { setStatusSaved(true); await cache.invalidateQueries(); },
  });
  const data = query.data;
  useEffect(() => { if (data) rememberDestination({ path: `${location.pathname}${location.search}`, title: data.name, paper: data.paper?.name ?? '', breadcrumb: [data.paper?.name, data.chapter?.name, data.topic?.name].filter(Boolean).join(' / ') }); }, [data, location.pathname, location.search]);
  useEffect(() => { if (data && published.data) restoreOrigin(`${location.pathname}${location.search}`); }, [data, published.data, location.pathname, location.search]);
  const appearances = [...new Map(data?.appearances.map(item => [item.question_id ?? `legacy:${item.id}`, item]) ?? []).values()];
  const questionRows = published.data?.items ?? [];
  const tabs = ['questions', 'notes', 'importance', 'references'];
  return <div className="space-y-4"><PageState loading={query.isPending} refreshing={query.isFetching && Boolean(data)} error={query.error} retry={() => query.refetch()} />{data && <>
    <section className="card space-y-3"><p className="study-meta">{sourceNode?.breadcrumbs.map(item => item.name).join(' / ') || [data.paper?.name, data.chapter?.name, data.topic?.name].filter(Boolean).join(' / ')}</p><h2 className="text-xl font-semibold">{data.name}</h2><div className="controls"><label>Progress <select aria-label="Progress" disabled={progress.isPending} value={data.status} onChange={e => progress.mutate(e.target.value as Status)}><option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="done">Done</option></select></label>{progress.isPending && <span role="status">Saving progress…</span>}{statusSaved && <span role="status">Progress saved.</span>}</div>{progress.error && <p role="alert">Progress was not saved: {progress.error.message}</p>}</section>
    <div role="tablist" aria-label="Topic content" className="study-tabs" onKeyDown={event => { const index = tabs.indexOf(tab); const next = event.key === "ArrowRight" ? tabs[(index + 1) % tabs.length] : event.key === "ArrowLeft" ? tabs[(index + tabs.length - 1) % tabs.length] : event.key === "Home" ? tabs[0] : event.key === "End" ? tabs[tabs.length - 1] : ""; if (next) { event.preventDefault(); set({ tab: next }); requestAnimationFrame(() => document.getElementById('topic-tab-' + next)?.focus()); } }}>{[['questions','Questions'],['notes','My notes'],['importance','Importance'],['references','Textbook references']].map(([id,label]) => <button key={id} role="tab" tabIndex={tab === id ? 0 : -1} id={'topic-tab-' + id} aria-controls="topic-panel" aria-selected={tab === id} onClick={() => set({ tab: id })}>{label}</button>)}</div>
    <section role="tabpanel" id="topic-panel" aria-labelledby={`topic-tab-${tab}`} className="card space-y-3">
    {tab === 'notes' && <><h3 className="font-semibold">My notes</h3><div className="controls"><button aria-pressed={!preview} onClick={() => setPreview(false)}>Write</button><button aria-pressed={preview} onClick={() => setPreview(true)}>Preview</button><button className="action" disabled={!dirty || saveStatus === 'saving'} onClick={() => { void save(); }}>{saveStatus === 'failed' ? 'Retry save' : 'Save notes'}</button></div>{preview ? <div className="reader-body whitespace-pre-wrap"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text || 'No notes yet.'}</ReactMarkdown></div> : <textarea aria-label="Notes" className="field w-full min-h-48" value={text} onChange={e => { const next = e.target.value; latest.current = next; setText(next); const draft = drafts.get(key); drafts.set(key, { text: next, saved: draft?.saved ?? data.notes ?? '' }); setSaveStatus('unsaved'); }} />}<p role="status">{saveStatus === 'failed' ? `Save failed: ${noteError}` : saveStatus === 'unsaved' ? 'Unsaved' : saveStatus === 'saving' ? 'Saving…' : 'Saved'}</p></>}
    {tab === 'importance' && <><h3 className="font-semibold">Importance</h3><StudyContext data={data as SubtopicData & StudyContextFields} /><PageState loading={why.isPending} error={why.error} retry={() => why.refetch()} />{why.data && <ScoreExplanation data={why.data} />}<button hidden aria-expanded={whyExpanded} onClick={() => setWhyExpanded(!whyExpanded)}>Why this importance?</button></>}
    {tab === 'references' && <><h3 className="font-semibold">Textbook references</h3><PageState loading={sources.isLoading || versions.isLoading} error={sources.error ?? versions.error} retry={() => { sources.refetch();versions.refetch(); }} />{sourceNode?.sources.length ? <TextbookSources sources={sourceNode.sources} /> : <><p>Reviewed textbook references are unavailable for this topic’s bound taxonomy.</p><Link className="topic-link" to={demoLink(`/syllabus?preview=draft&paper=${encodeURIComponent(data.paper?.code ?? '')}`)}>Preview textbook sources and edition applicability</Link></>}</>}
    {tab === 'questions' && <><h3 className="font-semibold">Questions</h3><PageState loading={published.isPending} error={published.error} retry={() => published.refetch()} />{questionRows.map(question => { const related = [...new Map(data.appearances.filter(item => item.question_id === question.question_id).map(item => [item.part_id ?? item.display_label, item])).values()]; const parts = [...new Set(related.map(item => item.display_label))]; return <div className="study-row" key={question.question_id}><h4 className="font-semibold">{question.display_label}</h4><p className="study-meta">{question.attempt_id ?? 'Undated collection'} · {question.source_family.replace(/_/g,' ')} · Answer {question.answer_status}</p>{parts.length > 0 && <p>Relevant parts: {parts.join(', ')}</p>}<p className="study-meta">{related.length ? related.map(item => item.marks == null ? 'Marks not available' : `${item.display_label}: ${item.marks} marks`).join(' · ') : question.marks?.whole_question_marks == null ? 'Marks not available' : String(question.marks.whole_question_marks) + " marks"}</p><Link className="topic-link" id={"topic-question-" + question.question_id} onClick={() => preserveOrigin(location.pathname + location.search, "topic-question-" + question.question_id)} to={demoLink(`/questions/${encodeURIComponent(question.question_id)}?${new URLSearchParams({ return: `${location.pathname}${location.search}` })}`)}>Read complete question</Link></div>; })}{published.data && published.data.total > 20 && <div className="controls"><button disabled={questionPage <= 1} onClick={() => set({ question_page: String(questionPage - 1) })}>Previous questions</button><span className="study-meta">Page {questionPage} · {published.data.total} questions</span><button disabled={questionPage * 20 >= published.data.total} onClick={() => set({ question_page: String(questionPage + 1) })}>Next questions</button></div>}{!published.isPending && !questionRows.length && <><p>Reviewed questions will appear here after publication.</p><Link className="topic-link" to={demoLink(`/questions?paper_id=${encodeURIComponent(data.paper?.id ?? '')}&subtopic_id=${encodeURIComponent(nodeId)}`)}>Browse questions</Link></>}{appearances.filter(item => !item.question_id).length > 0 && <details><summary>Legacy appearances without reviewed publication</summary>{appearances.filter(item => !item.question_id).map(item => <p key={item.id}>{item.display_label} · {item.attempt_id} · {item.provenance_limitation ?? 'Reliable complete-question source evidence is unavailable.'}</p>)}</details>}</>}

    </section>
  </>}
  <Dialog open={blocker.state === 'blocked'} title="Unsaved notes" onClose={() => { if (blocker.state === 'blocked') blocker.reset(); }}><p>Your draft has unsaved changes.</p><div className="controls"><button onClick={() => { if (blocker.state === 'blocked') blocker.reset(); }}>Stay</button><button className="action" disabled={saveStatus === 'saving'} onClick={async () => { const saved = await save(); if (saved && blocker.state === 'blocked') blocker.proceed(); }}>Save and leave</button><button disabled={saveStatus === 'saving'} onClick={() => { const draft = drafts.get(key); if (draft) drafts.set(key, { text: draft.saved, saved: draft.saved }); if (blocker.state === 'blocked') blocker.proceed(); }}>Discard and leave</button></div>{saveStatus === 'failed' && <p role="alert">Save failed: {noteError}. Your draft is retained.</p>}</Dialog>
  </div>;
}
