import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiRequest, accountKey, refreshIdentity, announceIdentityChange, type components } from '@caf/api-client';
import { isDemoMode } from '../lib/demo';
import { PageState } from '../components/PageState';

type Settings = components['schemas']['ProfileSettings'];
export function Profile() {
  const cache = useQueryClient();
  const demo = isDemoMode();
  const settings = useQuery({ queryKey: ['settings', accountKey()], queryFn: () => apiRequest<Settings>('/api/v1/me/settings'), enabled: !demo });
  const [draft, setDraft] = useState<Settings | null>(null);
  const [intervals, setIntervals] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (settings.data) { setDraft(settings.data); setIntervals(settings.data.revision_intervals.join(', ')); } }, [settings.data]);
  if (demo) return <p>Profile settings are available after signing in. Demo data stays local.</p>;
  const save = async () => {
    if (!draft || saving) return;
    setSaving(true); setError(''); setMessage('');
    try {
      const { groups: _groups, available_attempts: _attempts, available_papers: _papers, ...payload } = draft;
      const saved = await apiRequest<Settings>('/api/v1/me/settings', { method: 'PUT', body: JSON.stringify({ ...payload, revision_intervals: intervals.split(',').map(value => Number(value.trim())) }) });
      setDraft(saved); await cache.invalidateQueries(); await refreshIdentity(); announceIdentityChange(); setMessage('Profile settings saved.');
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not save profile.'); }
    finally { setSaving(false); }
  };
  const download = async () => {
    setError('');
    try {
      const data = await apiRequest<unknown>('/api/v1/me/export');
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = `study-profile-${accountKey()}.json`; link.click(); URL.revokeObjectURL(url);
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not export profile.'); }
  };
  return <div className="space-y-5"><h1 className="page-title">My profile</h1><PageState loading={settings.isPending} error={settings.error} retry={() => void settings.refetch()} />
    {draft && <form className="card space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <label className="block">Display name <input className="field" required value={draft.display_name} onChange={event => setDraft({ ...draft, display_name: event.target.value })} /></label>
      <label className="block">Target attempt <select className="field" value={draft.target_attempt_id} onChange={event => setDraft({ ...draft, target_attempt_id: event.target.value })}>{draft.available_attempts.map(attempt => <option key={attempt.id} value={attempt.id}>{attempt.label}</option>)}</select></label>
      <p className="text-sm">A planning target does not imply an official exam date or complete study material. Scores appear only when a successful run exists for your target.</p>
      <fieldset className="space-y-2"><legend className="font-bold">Selected papers</legend>{draft.available_papers.map(paper => <label key={paper.id} className="block"><input type="checkbox" checked={draft.selected_paper_ids.includes(paper.id)} onChange={event => setDraft({ ...draft, selected_paper_ids: event.target.checked ? [...draft.selected_paper_ids, paper.id] : draft.selected_paper_ids.filter(id => id !== paper.id) })} /> {paper.code} — {paper.name}</label>)}</fieldset>
      <label className="block">Weekly hours <input className="field" required type="number" min="0.01" step="any" value={draft.hours_per_week} onChange={event => setDraft({ ...draft, hours_per_week: Number(event.target.value) })} /></label>
      <label className="block">Minutes per subtopic <input className="field" required type="number" min="0.01" step="any" value={draft.minutes_per_subtopic} onChange={event => setDraft({ ...draft, minutes_per_subtopic: Number(event.target.value) })} /></label>
      <label className="block">Revision intervals in days <input className="field" required value={intervals} onChange={event => setIntervals(event.target.value)} /></label>
      <p className="text-sm">Enter positive, increasing intervals separated by commas.</p>
      <label className="block">Exam start date (optional) <input className="field" type="date" value={draft.exam_start_date ?? ''} onChange={event => setDraft({ ...draft, exam_start_date: event.target.value || null })} /></label>
      <button className="action" disabled={saving}>{saving ? 'Saving…' : 'Save profile'}</button>
    </form>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <button className="action" onClick={() => void download()}>Export my study records</button>
  </div>;
}
