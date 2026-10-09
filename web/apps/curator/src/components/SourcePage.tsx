import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { accountKey } from "@caf/api-client";
import { extractionApi } from "@caf/api-client/src/extraction";
import { RequestError } from "./RequestError";
const panel = "rounded-xl border border-slate-700 bg-slate-800 p-4 space-y-3";
const control = "rounded-lg border border-slate-600 bg-slate-900 p-2 text-sm";
export function SourcePage({ document, page, pageCount, change }: { document: number; page: number; pageCount: number | null; change: (page: number) => void }) {
  const [url, setUrl] = useState("");
  const source = useQuery({ queryKey: ["extraction-source-page", accountKey(), document, page], queryFn: () => extractionApi.page(document, page), retry: false });
  useEffect(() => {
    setUrl("");
    if (!source.data) return;
    const next = URL.createObjectURL(source.data); setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [source.data]);
  return <section className={panel} aria-label="Original source page"><h2 className="font-semibold">Original source · document {document}</h2><div className="flex items-center gap-2"><button className={control} disabled={page <= 1} onClick={() => change(page - 1)}>Previous page</button><label>Page <input className={`${control} w-20`} type="number" min={1} max={pageCount ?? undefined} value={page} onChange={event => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && (pageCount === null || value <= pageCount)) change(value); }} /></label><button className={control} disabled={pageCount !== null && page >= pageCount} onClick={() => change(page + 1)}>Next page</button></div><RequestError error={source.error} retry={() => void source.refetch()} />{source.isFetching && <p role="status">Loading original page…</p>}{url && <img className="w-full bg-white" src={url} alt={`Original document ${document}, page ${page}`} />}</section>;
}
