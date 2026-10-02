/** One cookie-backed identity lifecycle, shared by both applications. */
export type Account = { id: number; name: string; email: string | null; role: 'student' | 'administrator'; status: string };
export type Identity = { account: Account; capabilities: string[]; csrf_token: string };
export type AuthState = { status: 'loading' | 'active' | 'signed_out' | 'disabled' | 'invite_required' | 'error'; identity: Identity | null; message?: string };
let state: AuthState = { status: 'loading', identity: null };
let generation = 0;
let refreshPending: Promise<void> | null = null;
const listeners = new Set<() => void>();
const resets = new Set<() => void>();
const controllers = new Set<AbortController>();
const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('caf-identity') : null;
export const authState = () => state;
export const authGeneration = () => generation;
export const accountKey = () => state.identity?.account.id ?? 'anonymous';
export const subscribeAuth = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const onIdentityReset = (reset: () => void) => { resets.add(reset); return () => { resets.delete(reset); }; };
function update(next: AuthState) {
  const changed = state.identity?.account.id !== next.identity?.account.id || state.identity?.account.role !== next.identity?.account.role;
  if (changed) {
    generation++;
    controllers.forEach(controller => controller.abort());
    controllers.clear();
    resets.forEach(reset => reset());
  }
  state = next;
  listeners.forEach(listener => listener());
}
export function sessionExpired() { update({ status: 'signed_out', identity: null, message: 'Your session expired. Sign in again.' }); }
export async function refreshIdentity() {
  if (refreshPending) return refreshPending;
  const expected = generation;
  refreshPending = (async () => {
    try {
      const response = await fetch('/api/v1/me', { credentials: 'same-origin', cache: 'no-store' });
      if (expected !== generation) return;
      if (response.ok) {
        const identity: Identity = await response.json();
        if (expected === generation) {
          const changed = state.identity?.account.id !== identity.account.id || state.identity?.account.role !== identity.account.role;
          update({ status: 'active', identity });
          if (changed) announce();
        }
      }
      else {
        const detail = (await response.json()).detail;
        if (expected !== generation) return;
        update({ status: detail === 'account_disabled' ? 'disabled' : detail === 'invite_required' ? 'invite_required' : response.status === 401 ? 'signed_out' : 'error', identity: null, message: response.status === 401 ? 'Sign in to your private profile.' : detail });
      }
    } catch (error) {
      if (expected === generation) update({ status: 'error', identity: state.identity, message: error instanceof Error ? error.message : 'Could not check sign-in.' });
    } finally { refreshPending = null; }
  })();
  return refreshPending;
}
function announce(force = false) {
  const event = { accountId: state.identity?.account.id ?? null, role: state.identity?.account.role ?? null, force, stamp: `${Date.now()}:${Math.random()}` };
  channel?.postMessage(event);
  localStorage.setItem('caf_identity_event', JSON.stringify(event));
}
export async function logout() {
  if (!window.dispatchEvent(new Event('caf-before-logout', { cancelable: true }))) return;
  const csrf = state.identity?.csrf_token;
  update({ status: 'signed_out', identity: null, message: 'Signed out.' });
  try {
    const response = await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf ?? '' } });
    if (!response.ok && response.status !== 401) throw new Error(`Sign-out failed (${response.status}).`);
  } catch (error) {
    update({ status: 'error', identity: null, message: `The server could not confirm sign-out. ${error instanceof Error ? error.message : 'Try again.'}` });
    throw error;
  } finally { announce(); }
}
export function announceIdentityChange() { announce(true); }
export const signInUrl = () => `/auth/login?return_to=${encodeURIComponent(window.location.pathname + window.location.search)}`;
/** Abort in-flight reads and reject late results when the active account changes. */
export async function authenticatedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const expected = generation;
  const controller = new AbortController();
  controllers.add(controller);
  const request = new Request(input, init);
  const signal = request.signal;
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) controller.abort();
  const headers = new Headers(request.headers);
  if (state.identity) headers.set('X-Expected-Account-ID', String(state.identity.account.id));
  if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method.toUpperCase()) && state.identity) headers.set('X-CSRF-Token', state.identity.csrf_token);
  try {
    const response = await fetch(request, { headers, signal: controller.signal, credentials: 'same-origin' });
    // Wait for the body as well as the headers before accepting a private response.
    await response.clone().arrayBuffer();
    if (expected !== generation) throw new DOMException('Identity changed', 'AbortError');
    if (response.status === 401) sessionExpired();
    if (response.status === 409 && (await response.clone().json().catch(() => ({}))).detail === 'identity_changed') await reloadIdentity();
    if (response.status === 403) {
      const detail = (await response.clone().json().catch(() => ({}))).detail;
      if (detail === 'account_disabled') update({ status: 'disabled', identity: null });
    }
    return response;
  } finally { controllers.delete(controller); signal.removeEventListener('abort', abort); }
}
async function reloadIdentity() {
  update({ status: 'loading', identity: null });
  if (refreshPending) await refreshPending;
  await refreshIdentity();
}
if (typeof window !== 'undefined') {
  const receive = async (event: { accountId: number | null; role: string | null; force?: boolean }) => {
    const matchingAccount = event.accountId === (state.identity?.account.id ?? null) && event.role === (state.identity?.account.role ?? null);
    if (matchingAccount) {
      if (event.force) {
        await refreshIdentity();
        window.dispatchEvent(new Event('caf-profile-changed'));
      }
      return;
    }
    await reloadIdentity();
  };
  channel?.addEventListener('message', event => { void receive(event.data); });
  window.addEventListener('storage', event => { if (event.key === 'caf_identity_event' && event.newValue) void receive(JSON.parse(event.newValue)); });
  window.addEventListener('focus', () => { void refreshIdentity(); });
}
