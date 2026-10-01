import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getData, mode } from '../lib/data';
import type { MetaData } from '../lib/contracts';
import { PageState } from './PageState';
export function Diagnostics() {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState('');
  const location = useLocation();
  const query = useQuery({ queryKey: ['metadata', mode()], queryFn: () => getData<MetaData>('/api/v1/meta'), enabled: open });
  const value = JSON.stringify({ frontend_version: 'student-1.0.0', frontend_revision: import.meta.env.VITE_BUILD_REVISION ?? 'development', frontend_build: import.meta.env.VITE_BUILD_TIME ?? import.meta.env.VITE_BUILD_REVISION ?? 'development', api_version: query.data?.api_version ?? 'unavailable', backend_revision: query.data?.backend_revision ?? 'unavailable', route: location.pathname, browser: navigator.userAgent, mode: mode(), target_attempt: query.data?.target_attempt ?? null, score_run: query.data?.score_run ?? null, score_run_id: query.data?.score_run_id ?? null, score_run_computed_at: query.data?.score_run_computed_at ?? null }, null, 2);
  return <div><button className="text-xs" onClick={() => setOpen(!open)} aria-expanded={open}>Diagnostics</button>{open && <div className="card absolute right-4 top-14 max-w-xl max-h-[70vh] overflow-auto z-50 text-sm"><PageState loading={query.isPending} error={query.error} retry={() => query.refetch()} /><pre className="whitespace-pre-wrap">{value}</pre><button className="action" onClick={async () => { try { await navigator.clipboard.writeText(value); setCopied(true); setCopyError(''); } catch { setCopyError('Copy unavailable. Select the diagnostics text to copy it.'); } }}>Copy diagnostics</button>{copied && <p role="status">Copied.</p>}{copyError && <p role="alert">{copyError}</p>}</div>}</div>;
}
