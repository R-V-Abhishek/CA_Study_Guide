import { useState, useSyncExternalStore } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accountKey, authState, subscribeAuth } from "@caf/api-client";
import { taxonomyApi, type TextbookNode, type TextbookSource, type TextbookDescriptor, type TaxonomyDescriptor } from "@caf/api-client/src/taxonomy";
import "./textbook-explorer.css";

export function TaxonomyError({ error }: { error: unknown }) {
  return error ? <p role="alert" className="textbook-error">{error instanceof Error ? error.message : "The taxonomy request failed."}</p> : null;
}

export function TextbookSources({ sources }: { sources: TextbookSource[] }) {
  return <ul className="textbook-sources">{sources.map((source, index) => <li key={`${source.artifact_id}-${source.pdf_page_start}-${index}`}>
    <strong>{source.edition}</strong> · {source.fallback ? `${source.edition} fallback` : "Prescribed textbook source"}
    <p>Applicable attempts: {source.applicable_attempts.join(", ") || "Unresolved"} · May 2027 applicability: {source.target_applicability}</p>
    <p>Source review: {source.review_status} · Source availability: {source.availability}</p>
    <p>Source: {source.instrument || 'Official textbook'} · Edition {source.edition}</p>
    {source.instrument && <p>Instrument: {source.instrument}</p>}
    <a href={`${source.download_url.split("#")[0]}#page=${source.pdf_page_start}`} target="_blank" rel="noreferrer">Textbook PDF, pages {source.pdf_page_start}–{source.pdf_page_end}</a>
    {source.landing_url && <>{" · "}<a href={source.landing_url} target="_blank" rel="noreferrer">Official source page</a></>}
  </li>)}</ul>;
}

function HierarchyNode({ node, select }: { node: TextbookNode; select: (node: TextbookNode) => void }) {
  const label = <><span className="textbook-level">{node.level}</span> {node.name}</>;
  return <li>{node.children.length ? <details open={node.parent_id === null}>
    <summary>{label}</summary>
    <button className="textbook-link" type="button" onClick={() => select(node)}>View {node.name} context</button>
    <ul>{node.children.map(child => <HierarchyNode key={child.id} node={child} select={select} />)}</ul>
  </details> : <button type="button" className="textbook-node" onClick={() => select(node)}>{label}<span className="textbook-badge">{node.eligible ? "Classification ready" : "Review pending"}</span></button>}</li>;
}

function DescriptorEditor({ node, version, descriptor: original, sources, close }: { node: string; version: string; descriptor: TaxonomyDescriptor; sources: TextbookSource[]; close: () => void }) {
  const descriptor: TextbookDescriptor = original.status === "index_derived_draft_requires_review"
    ? { revision: original.revision, approved: false, definition: "", terminology: original.terminology,
        edition: original.source_edition, inclusion: [], exclusion: [], nearby_distinctions: [],
        source_spans: sources.map(({ artifact_id, pdf_page_start, pdf_page_end, review_status }) => ({ artifact_id, pdf_page_start, pdf_page_end, review_status })) }
    : original;
  const queries = useQueryClient();
  const [definition, setDefinition] = useState(descriptor.definition);
  const [terminology, setTerminology] = useState(descriptor.terminology.join("\n"));
  const [inclusion, setInclusion] = useState(descriptor.inclusion.join("\n"));
  const [exclusion, setExclusion] = useState(descriptor.exclusion.join("\n"));
  const [distinctions, setDistinctions] = useState(descriptor.nearby_distinctions.join("\n"));
  const [issues, setIssues] = useState((descriptor.source_ambiguities ?? []).join("\n"));
  const entries = (value: string) => value.split("\n").map(line => line.trim()).filter(Boolean);
  const save = useMutation({ mutationFn: () => taxonomyApi.editDescriptor(node, version, { definition: definition.trim(), terminology: entries(terminology), instrument_references: descriptor.instrument_references ?? [], edition: descriptor.edition ?? null, source_ambiguities: entries(issues), inclusion: entries(inclusion), exclusion: entries(exclusion), nearby_distinctions: entries(distinctions), source_spans: descriptor.source_spans }), onSuccess: async () => {
    await queries.invalidateQueries({ queryKey: ["textbook-descriptor", accountKey(), version, node] });
    await queries.invalidateQueries({ queryKey: ["textbook-tree", accountKey(), version] });
    close();
  } });
  return <form className="textbook-editor" onSubmit={event => { event.preventDefault(); save.mutate(); }}>
    <p>Saving creates an unapproved revision. Existing textbook citations stay attached.</p>
    <label>Concept definition<textarea aria-label="Concept definition" required value={definition} onChange={event => setDefinition(event.target.value)} /></label>
    <label>Terminology and instruments (one per line)<textarea aria-label="Terminology and instruments (one per line)" value={terminology} onChange={event => setTerminology(event.target.value)} /></label>
    <label>Inclusion guidance (one per line)<textarea aria-label="Inclusion guidance (one per line)" value={inclusion} onChange={event => setInclusion(event.target.value)} /></label>
    <label>Exclusion guidance (one per line)<textarea aria-label="Exclusion guidance (one per line)" value={exclusion} onChange={event => setExclusion(event.target.value)} /></label>
    <label>Nearby concept distinctions (one per line)<textarea aria-label="Nearby concept distinctions (one per line)" value={distinctions} onChange={event => setDistinctions(event.target.value)} /></label>
    <label>Unresolved textbook source issues (one per line)<textarea aria-label="Unresolved textbook source issues (one per line)" value={issues} onChange={event => setIssues(event.target.value)} /></label>
    <p>Remove a source issue only after checking the cited textbook and correcting the descriptor.</p>
    <div><button type="submit" className="textbook-action" disabled={save.isPending || !definition.trim()}>{save.isPending ? "Saving descriptor revision…" : "Save new descriptor revision"}</button>{" "}<button type="button" disabled={save.isPending} onClick={close}>Cancel descriptor edit</button></div><TaxonomyError error={save.error} />
  </form>;
}

export function TextbookNodeDetail({ node, version, curator }: { node: TextbookNode; version: string; curator: boolean }) {
  const queries = useQueryClient();
  const state = useSyncExternalStore(subscribeAuth, authState);
  const admin = state.identity?.capabilities.includes("admin");
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useState("sources");
  const descriptor = useQuery({ queryKey: ["textbook-descriptor", accountKey(), version, node.id], enabled: node.descriptor_revision !== null, retry: false, queryFn: () => taxonomyApi.descriptor(node.id, version) });
  const history = useQuery({ queryKey: ["textbook-history", accountKey(), version, node.id], retry: false, queryFn: () => taxonomyApi.history(node.id, version) });
  const indexDescriptor = descriptor.data?.status === "index_derived_draft_requires_review" ? descriptor.data : null;
  const explanation = descriptor.data?.status === "index_derived_draft_requires_review" ? null : descriptor.data;
  const approve = useMutation({ mutationFn: () => taxonomyApi.approveDescriptor(node.id, version, descriptor.data!.revision), onSuccess: async () => {
    await queries.invalidateQueries({ queryKey: ["textbook-descriptor", accountKey(), version, node.id] });
    await queries.invalidateQueries({ queryKey: ["textbook-tree", accountKey(), version] });
  } });
  const approveSource = useMutation({ mutationFn: () => taxonomyApi.approveSource(node.id, version), onSuccess: () => queries.invalidateQueries({ queryKey: ["textbook-tree", accountKey(), version] }) });
  return <section className="textbook-panel" aria-label="Selected textbook concept">
    <nav aria-label="Textbook breadcrumbs">{node.breadcrumbs.map(ancestor => ancestor.name).join(" → ")}</nav>
    <h2>{node.name}</h2><p>{node.level} · Source context: {node.source_review_status} · {node.eligible ? "Classification ready" : "Not eligible for classification"}</p>
    <p>Heading origin: {node.heading_origin === "app_authored" ? "App-authored concept subdivision" : node.heading_origin === "module_index" ? "Official module index heading" : node.heading_origin === "official" ? "Official textbook heading" : node.heading_origin === "legacy" ? "Legacy hierarchy" : "Unrecorded"}</p>
    <div role="tablist" aria-label="Syllabus evidence" className="study-tabs">{[["sources","Source references"],["descriptor","Descriptor"],["applicability","Applicability"],["history","History"]].map(([id,label]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>)}</div>
    {tab === "sources" && <>
    {node.sources.length ? <TextbookSources sources={node.sources} /> : <p>Textbook source span unresolved.</p>}
    {curator && admin && node.sources.length > 0 && node.source_review_status !== "reviewed" && <><button type="button" className="textbook-action" disabled={approveSource.isPending || node.sources.some(source => source.availability !== "verified")} onClick={() => approveSource.mutate()}>{approveSource.isPending ? "Recording source review…" : "Approve reviewed textbook source context"}</button><TaxonomyError error={approveSource.error} /></>}
    </>}
    {tab === "applicability" && <><h3>Applicability</h3>{node.sources.length ? node.sources.map((source,index) => <p key={index}>{source.edition} · Applicable attempts: {source.applicable_attempts.join(", ") || "Unresolved"} · Target applicability: {source.target_applicability} · {source.fallback ? "Fallback edition—requires applicability review" : "Prescribed source"}</p>) : <p>Edition applicability is unresolved.</p>}</>}
    {tab === "descriptor" && <>
    <h3>Descriptor</h3>
    <TaxonomyError error={descriptor.error} />
    {descriptor.isFetching && <p role="status">Loading descriptor…</p>}
    {node.descriptor_revision === null && <p>No classification descriptor. Containers are not classification labels.</p>}
    {descriptor.data && <div>
      <p>Revision {descriptor.data.revision} · {descriptor.data.approved ? "Approved" : "Review pending"}</p>
      {indexDescriptor && <section aria-label="Index heading evidence">
        <h4>Index heading evidence</h4>
        <p>This descriptor records the original index heading. A textbook explanation has not been authored or approved.</p>
        <dl><dt>Core concept</dt><dd>{indexDescriptor.core_concept}</dd><dt>Scope</dt><dd>{indexDescriptor.scope}</dd><dt>Terminology</dt><dd>{indexDescriptor.terminology.join(", ")}</dd><dt>Source edition</dt><dd>{indexDescriptor.source_edition}</dd><dt>Source attempts</dt><dd>{indexDescriptor.applicable_attempts.join(", ") || "Unresolved"}</dd><dt>Recorded status</dt><dd>{indexDescriptor.status}</dd><dt>Recorded applicability</dt><dd>{indexDescriptor.applicability_status}</dd></dl>
        <p>{indexDescriptor.note}</p>
        <p>May 2027 applicability requires review of the prescribed source edition.</p>
        <TextbookSources sources={node.sources} />
        {curator && <p>Author a textbook explanation before approving a descriptor. Saving creates a new revision requiring review.</p>}
      </section>}
      {explanation && <>
      <p>{explanation.definition}</p>
      {!!explanation.source_ambiguities?.length && <div><p>Textbook source issues must be resolved before approval.</p><ul>{explanation.source_ambiguities.map(issue => <li key={issue}>{issue}</li>)}</ul></div>}
      <dl><dt>Terminology</dt><dd>{explanation.terminology.join(", ") || "None recorded"}</dd><dt>Instruments</dt><dd>{explanation.instrument_references?.join(", ") || "None recorded"}</dd>{explanation.edition && <><dt>Textbook edition</dt><dd>{explanation.edition}</dd></>}<dt>Includes</dt><dd>{explanation.inclusion.join("; ")}</dd><dt>Excludes</dt><dd>{explanation.exclusion.join("; ")}</dd><dt>Nearby concepts</dt><dd>{explanation.nearby_distinctions.join("; ")}</dd></dl>
      <ul>{explanation.source_spans.map(span => { const source = node.sources.find(item => item.artifact_id === span.artifact_id); return <li key={`${span.artifact_id}-${span.pdf_page_start}`}>{source ? <a href={`${source.download_url.split("#")[0]}#page=${span.pdf_page_start}`} target="_blank" rel="noreferrer">Descriptor textbook reference, pages {span.pdf_page_start}–{span.pdf_page_end}</a> : `Textbook artifact ${span.artifact_id}, pages ${span.pdf_page_start}–${span.pdf_page_end}`}</li>; })}</ul>
      {curator && !explanation.approved && <><p>Approval records your review of this revision. Editing it requires a new approval.</p><button className="textbook-action" type="button" disabled={approve.isPending} onClick={() => approve.mutate()}>{approve.isPending ? "Recording approval…" : "Approve reviewed descriptor revision"}</button></>}
      </>}
      {curator && <p><button type="button" className="textbook-link" disabled={approve.isPending} onClick={() => setEditing(true)}>Edit descriptor</button></p>}
      {curator && editing && <DescriptorEditor node={node.id} version={version} descriptor={descriptor.data} sources={node.sources} close={() => setEditing(false)} />}
      <TaxonomyError error={approve.error} />
    </div>}
    </>}
    {tab === "history" && <>
    <h3>Legacy history and predecessor records</h3><TaxonomyError error={history.error} />
    {history.isFetching && <p role="status">Loading your history…</p>}
    {history.data && (history.data.records.length ? <ul>{history.data.records.map(record => <li key={`${record.node_id}-${record.relation}`}>
      <Link to={`/textbooks?${new URLSearchParams({ ...(record.relation === "current" ? { version } : { legacy: "true" }), paper: node.paper_id, node: record.node_id })}`}>{record.name}</Link> · {record.relation}
      <p>Original node: {record.node_id} · Progress: {record.progress?.status ?? "No progress recorded"}</p>
      {record.note && <blockquote><p>{record.note.body}</p><cite>Original note for {record.name} · {record.note.updated_at}</cite></blockquote>}
    </li>)}</ul> : <p>No predecessor records for your account.</p>)}
    </>}
  </section>;
}

export function TextbookExplorer({ curator = false, demo = false }: { curator?: boolean; demo?: boolean }) {
  const [params, setParams] = useSearchParams();
  const selection = params.get("version") ?? "";
  const paper = params.get("paper") ?? "";
  const selectedId = params.get("node") ?? "";
  const versions = useQuery({ queryKey: ["textbook-versions", accountKey()], enabled: !demo, retry: false, queryFn: taxonomyApi.versions });
  const version = selection || (params.get("legacy") === "true" ? versions.data?.find(item => item.status === "legacy")?.version_id : versions.data?.[0]?.version_id) || "";
  const tree = useQuery({ queryKey: ["textbook-tree", accountKey(), version], enabled: !demo && Boolean(version), retry: false, queryFn: () => taxonomyApi.tree(version) });
  const nodes = tree.data ?? [];
  const requestedPaper = /^P[1-6]$/i.test(paper) ? nodes.find(node => node.paper_id === paper.toUpperCase() || node.paper_id.endsWith(`.${paper.toUpperCase()}`))?.paper_id : paper;
  const paperId = requestedPaper || nodes[0]?.paper_id || "";
  function locate(items: TextbookNode[]): TextbookNode | undefined {
    for (const item of items) {
      if (item.id === selectedId) return item;
      const child = locate(item.children);
      if (child) return child;
    }
  }
  const roots = nodes.filter(node => node.paper_id === paperId);
  const current = locate(roots);
  const legacy = versions.data?.find(item => item.version_id === version)?.status === "legacy";
  const papers = [...new Map(nodes.map(node => [node.paper_id, node.level === "paper" ? node.name : node.paper_id])).entries()];
  return <div className={`textbook-explorer ${curator ? "textbook-curator" : ""}`}>
    <h1>{legacy ? "Legacy Taxonomy History" : "Textbook Taxonomy"}</h1><p>{legacy ? "Inspect the preserved previous hierarchy and your original personal records." : "Explore the independently sourced taxonomy. Review status and edition applicability are shown separately."}</p>
    <Link to="/textbooks?legacy=true">Legacy syllabus and history</Link>
    {(legacy || params.get("legacy") === "true") && <Link to="/textbooks">Current textbook taxonomy</Link>}
    {demo ? <p className="textbook-panel">Textbook source and review data require an authenticated session. Demo progress remains in the legacy syllabus.</p> : <>
      <TaxonomyError error={versions.error} /><TaxonomyError error={tree.error} />
      {versions.isPending && <p role="status">Loading taxonomy versions…</p>}
      {versions.data?.length === 0 && <p>No textbook taxonomy release has been drafted.</p>}
      {params.get("legacy") === "true" && versions.data && !version && <p>No legacy taxonomy snapshot is available.</p>}
      {versions.data && versions.data.length > 0 && <div className="textbook-controls">
        <label>Taxonomy version <select value={version} onChange={event => setParams({ version: event.target.value })}>{versions.data.map(item => <option key={item.version_id} value={item.version_id}>{item.version_id} · {item.status} · target {item.target_attempt}</option>)}</select></label>
        {papers.length > 0 && <label>Paper <select value={paperId} onChange={event => setParams({ version, paper: event.target.value })}>{papers.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>}
      </div>}
      {tree.isFetching && <p role="status">Loading textbook hierarchy…</p>}
      {tree.data?.length === 0 && <p>No textbook nodes available for this release. Unresolved sources remain in the source inventory.</p>}
      {tree.data && tree.data.length > 0 && <div className="textbook-columns"><section className="textbook-panel" aria-label="Recursive textbook hierarchy"><ul className="textbook-tree">{roots.map(node => <HierarchyNode key={node.id} node={node} select={item => setParams({ version, paper: paperId, node: item.id })} />)}</ul></section>
        {current ? <TextbookNodeDetail key={`${version}-${current.id}`} node={current} version={version} curator={curator} /> : <p>Select a concept to inspect its full ancestry, source span and review.</p>}
      </div>}
    </>}
  </div>;
}
