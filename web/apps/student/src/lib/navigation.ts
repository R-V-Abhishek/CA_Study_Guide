import { accountKey, onIdentityReset } from '@caf/api-client';
import { mode } from './data';
export interface ResumeDestination { path: string; title: string; paper: string; breadcrumb: string; context: string }
const prefix = () => `caf-navigation:${accountKey()}:`;
export function readNavigation<T>(key: string, fallback: T): T {
  try { const value = sessionStorage.getItem(prefix() + key); return value ? JSON.parse(value) as T : fallback; } catch { return fallback; }
}
export function writeNavigation(key: string, value: unknown) { try { sessionStorage.setItem(prefix() + key, JSON.stringify(value)); } catch { /* Navigation remains usable without storage. */ } }
export function rememberDestination(item: Omit<ResumeDestination, 'context'>) { writeNavigation('resume', { ...item, context: mode() }); }
export function resumeDestination() { const item = readNavigation<ResumeDestination | null>('resume', null); return item?.context === mode() ? item : null; }
export function preserveOrigin(path: string, row: string) { writeNavigation(`origin:${path}`, { scroll: window.scrollY, row }); }
export function restoreOrigin(path: string) { const state = readNavigation<{ scroll: number; row: string } | null>(`origin:${path}`, null); if (state) requestAnimationFrame(() => { document.getElementById(state.row)?.focus({ preventScroll: true }); window.scrollTo(0, state.scroll); }); }
onIdentityReset(() => { for (let index = sessionStorage.length - 1; index >= 0; index--) { const key = sessionStorage.key(index); if (key?.startsWith('caf-navigation:')) sessionStorage.removeItem(key); } });
