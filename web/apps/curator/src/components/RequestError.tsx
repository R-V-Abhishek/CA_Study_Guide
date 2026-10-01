export function RequestError({ error, retry }: { error: Error | null; retry?: () => void }) {
  if (!error) return null;
  return <div role="alert" className="p-4 rounded-xl border border-rose-800 bg-rose-950/50 text-rose-200 text-sm">
    <p>{error.message}</p>
    {retry && <button type="button" className="mt-2 underline" onClick={retry}>Retry</button>}
  </div>;
}
