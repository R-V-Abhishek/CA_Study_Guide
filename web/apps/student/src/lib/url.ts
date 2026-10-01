import { useSearchParams } from 'react-router-dom';
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
