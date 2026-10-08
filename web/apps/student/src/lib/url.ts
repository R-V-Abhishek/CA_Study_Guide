import { useSearchParams } from 'react-router-dom';
export function internalReturn(value: string | null, fallback = '/questions'): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u001f]/.test(value)) return fallback;
  const url = new URL(value, window.location.origin);
  return url.origin === window.location.origin && /^\/(questions|papers|plan|progress|revision|textbooks|syllabus)(\/|\?|$)/.test(value) ? `${url.pathname}${url.search}${url.hash}` : fallback;
}
export function useUrlState() {
  const [params, setParams] = useSearchParams();
  const set = (values: Record<string, string>) => setParams(previous => {
    const next = new URLSearchParams(previous);
    for (const [key, value] of Object.entries(values)) {
      if (value === '' || value === 'all') next.delete(key); else next.set(key, value);
    }
    return next;
  });
  return { params, set, search: params.toString() ? `?${params}` : '' };
}
