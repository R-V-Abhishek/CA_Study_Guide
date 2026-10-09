import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { accountKey, authGeneration } from "@caf/api-client";
import { extractionApi } from "@caf/api-client/src/extraction";
import { RequestError } from "./RequestError";
const panel = "rounded-xl border border-slate-700 bg-slate-800 p-4 space-y-3";
const control = "rounded-lg border border-slate-600 bg-slate-900 p-2 text-sm";
export function SourcePage({ document, page, pageCount, change }: { document: number; page: number; pageCount: number | null; change: (page: number) => void }) {
  const [url, setUrl] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");
  const [pdfError, setPdfError] = useState<Error | null>(null);
  const [pdfPending, setPdfPending] = useState(false);
  const pdfObjectUrl = useRef("");
  const requestToken = useRef(0);
  const account = accountKey();
  const source = useQuery({ queryKey: ["extraction-source-page", accountKey(), document, page], queryFn: () => extractionApi.page(document, page), retry: false });
  useEffect(() => {
    setUrl("");
    if (!source.data) return;
    const next = URL.createObjectURL(source.data); setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [source.data]);
  useEffect(() => {
    requestToken.current += 1; setPdfUrl(""); setPdfError(null); setPdfPending(false);
    return () => { requestToken.current += 1; if (pdfObjectUrl.current) URL.revokeObjectURL(pdfObjectUrl.current); pdfObjectUrl.current = ""; };
  }, [document, account]);
  const openPdf = async () => {
    if (pdfPending) return;
    const popup = window.open("about:blank", "_blank");
    if (popup) { popup.opener = null; const policy = popup.document.createElement("meta"); policy.name = "referrer"; policy.content = "no-referrer"; popup.document.head.append(policy); popup.document.title = "Original source PDF"; popup.document.body.textContent = "Preparing original PDF…"; }
    const generation = authGeneration(); const token = requestToken.current;
    setPdfPending(true); setPdfError(null);
    try {
      const blob = await extractionApi.pdf(document);
      if (generation !== authGeneration() || token !== requestToken.current) { popup?.close(); return; }
      if (pdfObjectUrl.current) URL.revokeObjectURL(pdfObjectUrl.current);
      const next = URL.createObjectURL(blob); pdfObjectUrl.current = next; setPdfUrl(next);
      if (popup) popup.location.href = next;
    } catch (error) {
      popup?.close();
      if (generation === authGeneration() && token === requestToken.current) setPdfError(error as Error);
    } finally { if (generation === authGeneration() && token === requestToken.current) setPdfPending(false); }
  };
  return <section className={panel} aria-label="Original source page" aria-busy={source.isPending || pdfPending}><h2 className="font-semibold">Original source page</h2><details><summary>Technical source details</summary><p>Document {document}</p></details><div className="flex flex-wrap items-center gap-2"><button className={control} disabled={page <= 1} onClick={() => change(page - 1)}>Previous page</button><label>Page <input className={`${control} w-20`} type="number" min={1} max={pageCount ?? undefined} value={page} onChange={event => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && (pageCount === null || value <= pageCount)) change(value); }} /></label><button className={control} disabled={pageCount !== null && page >= pageCount} onClick={() => change(page + 1)}>Next page</button>{pdfUrl ? <a className={`${control} underline`} href={pdfUrl} target="_blank" rel="noreferrer">Open PDF</a> : <button type="button" className={control} disabled={pdfPending} onClick={() => void openPdf()}>{pdfPending ? "Preparing PDF…" : "Open PDF"}</button>}</div><RequestError error={pdfError} retry={() => void openPdf()} /><RequestError error={source.error} retry={() => void source.refetch()} />{source.isFetching && <p role="status">Loading original page…</p>}{url && <img className="w-full bg-white" src={url} alt={`Original document ${document}, page ${page}`} />}</section>;
}
