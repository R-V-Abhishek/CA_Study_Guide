export function RequestError({ error, retry, retryLabel = "Retry" }: { error: Error | null; retry?: () => void; retryLabel?: string }) {
  if (!error) return null;
  return <div role="alert" className="p-4 rounded-xl border border-rose-800 bg-rose-950/50 text-rose-200 text-sm">
    <p>{error.message}</p>
    {retry && <button type="button" className="mt-2 underline" onClick={retry}>{retryLabel}</button>}
  </div>;
}
