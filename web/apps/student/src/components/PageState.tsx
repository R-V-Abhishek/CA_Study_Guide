import './workspace.css';
export function PageState({ loading, refreshing, error, retry }: { loading?: boolean; refreshing?: boolean; error?: Error | null; retry?: () => unknown }) {
  if (error) return <div role="alert" className="card"><p>Unable to load: {error.message}</p>{retry && <button className="action" onClick={retry}>Retry</button>}</div>;
  if (loading) return <div role="status" aria-busy="true" className="card study-skeleton"><p className="study-meta">Loading…</p><span aria-hidden="true" /><span aria-hidden="true" /><span aria-hidden="true" /></div>;
  if (refreshing) return <p role="status" className="study-meta">Refreshing…</p>;
  return null;
}
