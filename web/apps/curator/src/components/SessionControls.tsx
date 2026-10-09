import { useState, useSyncExternalStore } from 'react';
import { authState, subscribeAuth, logout } from '@caf/api-client';

export function SessionControls() {
  const state = useSyncExternalStore(subscribeAuth, authState);
  const [error, setError] = useState('');
  if (!state.identity) return null;
  return <div className="session-controls"><a href="/profile">{state.identity.account.name} · Profile</a>
    {state.identity.capabilities.includes('admin') && <a href="/curator/accounts" className="underline">Accounts</a>}
    <button onClick={() => { void logout().catch(error => setError(error.message)); }}>Sign out</button>
    {error && <span role="alert">{error}</span>}
  </div>;
}
