import { accountKey } from "@caf/api-client";
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { curatorClient, requiredData } from "../lib/client";
import { Dialog } from '../../../../packages/workspace/Dialog';

export function Diagnostics() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [copyState, setCopyState] = useState("");
  const meta = useQuery({ queryKey: ["curator-meta", accountKey()], enabled: open, queryFn: async () => requiredData(await curatorClient.GET("/api/v1/meta")) });
  const info = JSON.stringify({
    frontend: { app: "curator", version: "1.0.0", revision: import.meta.env.VITE_BUILD_REVISION ?? "development", built_at: import.meta.env.VITE_BUILD_TIME ?? null },
    backend: { api_version: meta.data?.api_version ?? null, revision: meta.data?.backend_revision ?? null },
    route: location.pathname,
    browser: navigator.userAgent,
    target_attempt: meta.data?.target_attempt ?? null,
    score_run: meta.data?.score_run ?? null,
    metadata_status: meta.isPending ? "loading" : meta.isError ? "unavailable" : "available",
  }, null, 2);
  return <div className="text-xs">
    <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" className="secondary-action">Diagnostics</button>
    <Dialog title="Technical details" open={open} onClose={() => setOpen(false)}>
      <p>Build and API diagnostics</p><textarea aria-label="Diagnostics data" readOnly value={info} rows={15} className="w-full bg-slate-950 p-2 font-mono text-xs" />
      <button type="button" className="underline mr-4" onClick={async () => { try { await navigator.clipboard.writeText(info); setCopyState("Copied"); } catch { setCopyState("Copy unavailable. Select the text above to copy."); } }}>Copy diagnostics</button>
      <p role="status">{copyState}</p>
    </Dialog>
  </div>;
}
