/** Demo mode is explicit; fixtures never substitute for failed live requests. */
export const isDemoMode = () => ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname) && (new URLSearchParams(window.location.search).get('demo') === 'true' || import.meta.env.VITE_DEMO_MODE === 'true');
export const demoLink = (path: string) => {
  if (!isDemoMode()) return path;
  const url = new URL(path, window.location.origin);
  url.searchParams.set('demo', 'true');
  return url.pathname + url.search;
};
