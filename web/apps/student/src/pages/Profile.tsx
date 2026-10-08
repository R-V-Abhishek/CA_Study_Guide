import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest, accountKey, refreshIdentity, announceIdentityChange, authGeneration, type components } from '@caf/api-client';
import { isDemoMode } from '../lib/demo';
import { PageState } from '../components/PageState';
import { resetStudyContext, mode, getData } from '../lib/data';
import { exportProfile } from '../lib/export';
import { ThemeControl } from '../../../../packages/workspace/theme';

type Settings=components['schemas']['ProfileSettings'];
export function Profile() {
  const cache=useQueryClient();
  const demo=isDemoMode();
  const settings=useQuery({ queryKey:['settings',accountKey()],queryFn:() => apiRequest<Settings>('/api/v1/me/settings'),enabled:!demo });
  const context=useQuery({ queryKey:['profile-readiness',mode()],queryFn:() => getData<components['schemas']['Dashboard']>('/api/v1/dashboard'),enabled:!demo });
  const [draft,setDraft]=useState<Settings | null>(null);
  const [saved,setSaved]=useState<Settings | null>(null);
  const [intervals,setIntervals]=useState('');
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  const [exporting,setExporting]=useState(false);
  const generation=authGeneration();
  useEffect(() => { if (settings.data && !draft) { setDraft(settings.data);setSaved(settings.data);setIntervals(settings.data.revision_intervals.join(', ')); } },[settings.data,draft]);
  const intervalValues=intervals.split(',').map(value => Number(value.trim()));
  const validIntervals=intervalValues.length > 0 && intervalValues.every((value,index) => Number.isInteger(value) && value > 0 && (index === 0 || value > intervalValues[index - 1]));
  const dirty=Boolean(draft && saved && (JSON.stringify(draft) !== JSON.stringify(saved) || intervals !== saved.revision_intervals.join(', ')));
  const valid=Boolean(draft?.display_name.trim() && draft.selected_paper_ids.length && Number.isFinite(draft.hours_per_week) && draft.hours_per_week > 0 && Number.isInteger(draft.minutes_per_subtopic) && draft.minutes_per_subtopic > 0 && validIntervals);
  const save=async () => {
    if (!draft || saving || !valid) return;
    setSaving(true);setError('');setMessage('');
    try { const { groups:_groups,available_attempts:_attempts,available_papers:_papers,...payload }=draft;const response=await apiRequest<Settings>('/api/v1/me/settings',{ method:'PUT',body:JSON.stringify({ ...payload,revision_intervals:intervalValues }) });if (generation !== authGeneration()) return;await cache.cancelQueries();resetStudyContext();setDraft(response);setSaved(response);setIntervals(response.revision_intervals.join(', '));await refreshIdentity();await cache.invalidateQueries();announceIdentityChange();setMessage('Settings saved.'); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not save settings.'); }
    finally { setSaving(false); }
  };
  if (demo) return <div className="space-y-5"><h1 className="page-title">Settings</h1><p>Profile settings are available after signing in. Demo data stays local.</p><ThemeControl /></div>;
  return <div className="space-y-5"><h1 className="page-title">Settings</h1><p>Manage your profile, study target and preferences with an explicit save.</p><PageState loading={settings.isPending} error={settings.error} retry={() => settings.refetch()} />{draft && <form className="space-y-5" onSubmit={event => { event.preventDefault();void save(); }}><section className="card space-y-3"><h2 className="text-xl font-semibold">Profile</h2><label className="block">Display name <input className="field" required disabled={saving} value={draft.display_name} onChange={event => setDraft({ ...draft,display_name:event.target.value })} /></label></section><section className="card space-y-3"><h2 className="text-xl font-semibold">Exam target</h2><label className="block">Target attempt <select className="field" disabled={saving} value={draft.target_attempt_id} onChange={event => setDraft({ ...draft,target_attempt_id:event.target.value })}>{draft.available_attempts.map(attempt => <option key={attempt.id} value={attempt.id}>{attempt.label}</option>)}</select></label><p className="study-meta">{draft.target_attempt_id !== saved?.target_attempt_id ? 'Target readiness will be checked after Save.' : context.isPending ? 'Checking target readiness…' : context.data?.context?.readiness !== 'ready' ? 'The selected target syllabus is awaiting reviewed applicability and attempt binding. Preview remains available.' : 'Your target has a reviewed syllabus binding.'}</p><label className="block">Exam start date (optional) <input className="field" type="date" disabled={saving} value={draft.exam_start_date ?? ''} onChange={event => setDraft({ ...draft,exam_start_date:event.target.value || null })} /></label></section><section className="card space-y-3"><h2 className="text-xl font-semibold">Selected papers</h2>{[1,2].map(group => <fieldset key={group} disabled={saving}><legend className="font-semibold">Group {group}</legend>{draft.available_papers.filter(item => item.group_no === group).map(paper => <label key={paper.id} className="block py-2"><input type="checkbox" checked={draft.selected_paper_ids.includes(paper.id)} onChange={event => setDraft({ ...draft,selected_paper_ids:event.target.checked ? [...draft.selected_paper_ids,paper.id] : draft.selected_paper_ids.filter(id => id !== paper.id) })} /> {paper.code} — {paper.name}</label>)}</fieldset>)}</section><section className="card space-y-3"><h2 className="text-xl font-semibold">Study budget</h2><label className="block">Weekly hours <input className="field" required disabled={saving} type="number" min="0.01" step="any" value={draft.hours_per_week} onChange={event => setDraft({ ...draft,hours_per_week:Number(event.target.value) })} /></label><label className="block">Minutes per subtopic <input className="field" required disabled={saving} type="number" min="1" step="1" value={draft.minutes_per_subtopic} onChange={event => setDraft({ ...draft,minutes_per_subtopic:Number(event.target.value) })} /></label></section><section className="card space-y-3"><h2 className="text-xl font-semibold">Revision intervals</h2><label className="block">Revision intervals in days <input className="field" required disabled={saving} value={intervals} onChange={event => setIntervals(event.target.value)} /></label><p className="study-meta">Enter positive, increasing whole-day intervals separated by commas.</p>{!validIntervals && <p role="alert">Revision intervals must be positive and increasing.</p>}</section><div className="controls"><button className="action" disabled={saving || !dirty || !valid}>{saving ? 'Saving…' : 'Save settings'}</button><p role="status">{saving ? 'Saving…' : error ? 'Save failed. Your changes are retained.' : dirty ? 'Unsaved' : message || 'Saved'}</p></div></form>}{error && <p role="alert">{error}</p>}<section className="card space-y-3"><h2 className="text-xl font-semibold">Appearance</h2><ThemeControl /></section><section className="card space-y-3"><h2 className="text-xl font-semibold">Export</h2><p>Download your authenticated personal study records.</p><button disabled={exporting} onClick={async () => { setExporting(true);setError('');try { await exportProfile(); }catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not export profile.'); }finally { setExporting(false); } }}>{exporting ? 'Exporting…' : 'Export my study records'}</button></section></div>;
}
