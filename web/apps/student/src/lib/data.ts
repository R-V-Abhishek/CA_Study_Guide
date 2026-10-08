import { useQuery } from '@tanstack/react-query';
import { apiRequest, accountKey } from '@caf/api-client';
import { isDemoMode } from './demo';
import { demoResponse } from './fixtures';
import type { PaperSummary, PaperTree } from './contracts';
let contextGeneration = 0;
export const resetStudyContext = () => { contextGeneration++; };
if (typeof window !== 'undefined') window.addEventListener('caf-profile-changed', resetStudyContext);
export const mode = () => isDemoMode() ? 'demo' : `live:${accountKey()}:context:${contextGeneration}`;
export function getData<T>(url: string, signal?: AbortSignal): Promise<T> {
  return isDemoMode() ? Promise.resolve(demoResponse<T>(url)) : apiRequest<T>(url, { signal });
}
export function usePapers() {
  return useQuery({ queryKey: ['papers', mode()], queryFn: () => getData<PaperSummary[]>('/api/v1/papers') });
}
export function treeUrl(id: string) {
  return /^P\d+$/i.test(id) ? `/api/v1/tree?paper=${encodeURIComponent(id)}` : `/api/v1/papers/${encodeURIComponent(id)}/tree`;
}
export const getTree = (id: string) => getData<PaperTree>(treeUrl(id));
export const jsonOptions = (method: string, body: unknown) => ({ method, body: JSON.stringify(body) });
export const formatPct = (value: number | null | undefined) => value == null ? 'Unavailable' : `${value.toFixed(1)}%`;
export const importance = (value: number | null | undefined) => value == null ? 'Unavailable' : `${(value * 100).toFixed(1)} / 100`;
