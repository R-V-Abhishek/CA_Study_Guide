import { useEffect, useSyncExternalStore, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { authState, subscribeAuth, onIdentityReset, refreshIdentity, signInUrl } from '@caf/api-client';

export function AuthGate({ children, demo = false }: { children: ReactNode; demo?: boolean }) {
  const state = useSyncExternalStore(subscribeAuth, authState);
  const cache = useQueryClient();
  useEffect(() => onIdentityReset(() => { void cache.cancelQueries(); cache.clear(); }), [cache]);
  useEffect(() => {
    const refresh = () => { void cache.invalidateQueries(); };
    window.addEventListener('caf-profile-changed', refresh);
    return () => window.removeEventListener('caf-profile-changed', refresh);
  }, [cache]);
  useEffect(() => { if (!demo) void refreshIdentity(); }, [demo]);
  if (demo) return <>{children}</>;
  if (state.status === 'active') return <div key={`${state.identity!.account.id}:${state.identity!.account.role}`}>{children}</div>;
  return <main className="min-h-screen p-8 space-y-4 bg-stone-50 text-stone-900"><h1 className="text-2xl font-bold">CA Final Prep</h1>
    {state.status === 'loading' ? <p role="status">Checking sign-in…</p> : <>
      <h2 className="text-xl">{state.status === 'disabled' ? 'Account disabled' : state.status === 'invite_required' ? 'Invitation required' : state.status === 'error' ? 'Sign-in unavailable' : 'Sign in'}</h2>
      <p>{state.message ?? (state.status === 'disabled' ? 'An administrator must restore access to this account.' : state.status === 'invite_required' ? 'Open the invitation link supplied by your administrator.' : 'Use your invited account to access your private study profile.')}</p>
      {state.status !== 'disabled' && <a className="underline" href={signInUrl()}>Sign in with Auth0</a>}
      <button onClick={() => void refreshIdentity()} className="underline ml-4">Check again</button>
    </>}
  </main>;
}
