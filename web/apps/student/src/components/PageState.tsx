export function PageState({ loading, error, retry }: { loading?: boolean; error?: Error | null; retry?: () => unknown }) {
  if (loading) return <p role="status" className="card">Loading…</p>;
  if (error) return <div role="alert" className="card text-red-700"><p>Unable to load: {error.message}</p><button onClick={retry}>Retry</button></div>;
  return null;
}
