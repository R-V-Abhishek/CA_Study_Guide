import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accountKey } from "@caf/api-client";
import { taxonomyApi } from "@caf/api-client/src/taxonomy";
import { TaxonomyError } from "../../../student/src/components/TextbookExplorer";

export function TaxonomyRelease() {
  const queries = useQueryClient();
  const [selection, setSelection] = useState("");
  const [acknowledgedHash, setAcknowledgedHash] = useState("");
  const versions = useQuery({ queryKey: ["textbook-versions", accountKey()], retry: false, queryFn: taxonomyApi.versions });
  const version = selection || versions.data?.[0]?.version_id || "";
  const report = useQuery({ queryKey: ["textbook-report", accountKey(), version], enabled: Boolean(version), retry: false, queryFn: () => taxonomyApi.report(version) });
  const crosswalk = useQuery({ queryKey: ["textbook-crosswalk", accountKey(), version], enabled: Boolean(version), retry: false, queryFn: () => taxonomyApi.crosswalk(version) });
  const sources = useQuery({ queryKey: ["textbook-sources", accountKey(), version], enabled: Boolean(version), retry: false, queryFn: () => taxonomyApi.sources(version) });
  const questionSources = useQuery({ queryKey: ["taxonomy-question-sources", accountKey(), version], enabled: Boolean(version), retry: false, queryFn: () => taxonomyApi.questionSources(version) });
  const sourceFamilies = { model: "Model Test Papers", mock: "Mock Test Papers", rtp: "RTPs", past_exam: "Past examinations", case_study: "Case studies and practice" };
  const sourceQueues = { final_metadata_review: "Final source awaiting metadata review", outside_corpus: "Outside the Final corpus", not_question_artifact: "Not a question artifact" };
  const approve = useMutation({ mutationFn: () => taxonomyApi.approve(version, report.data!.manifest_hash), onSuccess: async () => {
    setAcknowledgedHash("");
    await queries.invalidateQueries({ queryKey: ["textbook-report", accountKey(), version] });
    await queries.invalidateQueries({ queryKey: ["textbook-versions", accountKey()] });
  } });
  const approveMapping = useMutation({ mutationFn: (mapping: number) => taxonomyApi.approveCrosswalk(mapping, version), onSuccess: () => queries.invalidateQueries({ queryKey: ["textbook-crosswalk", accountKey(), version] }) });
  return <div className="textbook-explorer textbook-curator">
    <h1>Source & Release Review</h1><p>Review textbook coverage and personal-data migration before approving a specific release manifest.</p>
    <Link to="/textbooks">Inspect textbook hierarchy and descriptors</Link>
    <TaxonomyError error={versions.error} />
    {versions.isPending && <p role="status">Loading taxonomy versions…</p>}
    {versions.data?.length === 0 && <p>No textbook taxonomy release has been drafted.</p>}
    {versions.data && versions.data.length > 0 && <div className="textbook-controls"><label>Taxonomy version <select value={version} onChange={event => { setSelection(event.target.value); setAcknowledgedHash(""); approve.reset(); }}>{versions.data.map(item => <option key={item.version_id} value={item.version_id}>{item.version_id} · {item.status} · target {item.target_attempt}</option>)}</select></label></div>}
    <section className="textbook-panel"><h2>Textbook source inventory</h2><TaxonomyError error={sources.error} />{sources.isFetching && <p role="status">Loading textbook sources…</p>}
      {sources.data?.length === 0 && <p>No textbook artifacts recorded for this release.</p>}
      {sources.data && sources.data.length > 0 && <div className="textbook-table-wrap"><table><thead><tr><th>Paper and edition</th><th>Availability and applicability</th><th>Expected structure and evidence</th></tr></thead><tbody>{sources.data.map(source => <tr key={source.id}><td><strong>{source.paper_id}</strong> · {source.course_level}<p>{source.edition}</p><p>Applicable attempts: {source.applicable_attempts.join(", ") || "Unresolved"}</p><a href={source.landing_url} target="_blank" rel="noreferrer">Official page</a>{" · "}<a href={source.download_url} target="_blank" rel="noreferrer">Textbook PDF</a></td><td>{source.availability}<p>{source.fallback ? "January 2026 fallback" : "Target textbook selection"}</p><p>May 2027 applicability: {source.target_applicability}</p>{source.instrument && <p>Instrument: {source.instrument}</p>}{source.retrieval_error && <p>{source.retrieval_error}</p>}</td><td><p>Retrieved: {source.retrieved_at} · Pages: {source.page_count ?? "Unverified"}</p><p>SHA-256: <code>{source.sha256 ?? "Not verified"}</code></p><p>Heading reconciliation: {source.heading_reconciliation.status} · {source.heading_reconciliation.accounted_count}/{source.heading_reconciliation.expected_count} expected headings accounted for</p><details><summary>Unresolved heading checks ({source.heading_reconciliation.unresolved.length})</summary><ul>{source.heading_reconciliation.unresolved.map((gap, index) => <li key={index}>{gap}</li>)}</ul></details><details><summary>Expected textbook structure ({source.expected_structure.length})</summary><ul>{source.expected_structure.map((heading, index) => <li key={index}>{[heading.module, heading.chapter, heading.name].filter(Boolean).join(" → ")} ({heading.kind})</li>)}</ul></details><details><summary>Edition evidence</summary><ul>{source.edition_evidence.map(url => <li key={url}><a href={url} target="_blank" rel="noreferrer">Official edition evidence</a></li>)}</ul></details></td></tr>)}</tbody></table></div>}
    </section>
    <section className="textbook-panel"><h2>Question-source inventory</h2><p>Model and mock papers remain distinct practice families. Undated sources keep their original attempt unspecified.</p><TaxonomyError error={questionSources.error} />{questionSources.isFetching && <p role="status">Loading question-source inventory…</p>}
      {questionSources.data?.length === 0 && <p>No question-source artifacts recorded for this release.</p>}
      {questionSources.data && questionSources.data.length > 0 && <div className="textbook-table-wrap"><table><thead><tr><th>Family and course</th><th>Attempt and paper</th><th>Artifact and pairing</th><th>Availability and routing</th></tr></thead><tbody>{questionSources.data.map(source => <tr key={source.id}><td>{sourceFamilies[source.source_family]}<p>{source.course_level}</p><p>Scheme: {source.scheme_id ?? "Unspecified"}</p></td><td>Attempt: {source.attempt_id ?? "Undated"}<p>Paper: {source.paper_id ?? (source.paper_ids.length ? source.paper_ids.join(", ") : "Unresolved")}</p><p>Group: {source.group ?? "Unspecified"} · Series: {source.series ?? "Unspecified"}</p></td><td>{source.artifact_role.replace(/_/g, " ")}<p>Identity: <code>{source.id}</code></p><p>Paired artifact: {source.paired_artifact_id ?? "Unpaired"}</p><a href={source.landing_url} target="_blank" rel="noreferrer">Official source page</a>{source.download_url && <>{" · "}<a href={source.download_url} target="_blank" rel="noreferrer">Artifact download</a></>}</td><td>{source.availability}<p>{sourceQueues[source.classification_queue]}</p><p>Retrieved: {source.retrieved_at} · Pages: {source.page_count ?? "Unverified"}</p><p>SHA-256: <code>{source.sha256 ?? "Not verified"}</code></p></td></tr>)}</tbody></table></div>}
    </section>
    <TaxonomyError error={report.error} />
    {report.isFetching && <p role="status">Loading release report…</p>}
    {report.data && <section className="textbook-panel" aria-label="Release and migration report">
      <h2>Release and migration report</h2><p>Status: {report.data.status}</p><p>Manifest hash: <code>{report.data.manifest_hash}</code></p>
      <dl><dt>Textbook hierarchy</dt><dd>{report.data.node_count} nodes · {report.data.source_count} textbook sources · {report.data.unresolved_sources.length} unverified recorded artifacts</dd><dt>Classification readiness</dt><dd>{report.data.eligible_count} eligible subtopics · {report.data.unreviewed_descriptors.length} unreviewed descriptors</dd><dt>Preserved legacy records</dt><dd>{report.data.legacy_progress_count === null || report.data.legacy_note_count === null ? "Private record counts are not exposed to administrators. Review preservation in the checkpoint audit." : `${report.data.legacy_progress_count} progress records · ${report.data.legacy_note_count} original notes`}</dd></dl>
      <h3>Release blockers</h3>{report.data.blockers.length ? <ul>{report.data.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul> : <p>No blockers recorded.</p>}
      <p>Split, merge and unresolved mappings retain predecessor history. Completion carries forward only through reviewed exact equivalence.</p>
      <label><input type="checkbox" checked={acknowledgedHash === report.data.manifest_hash} disabled={approve.isPending || !report.data.activation_ready} onChange={event => setAcknowledgedHash(event.target.checked ? report.data.manifest_hash : "")} /> I reviewed this manifest and its migration report.</label><br />
      <button className="textbook-action" type="button" disabled={acknowledgedHash !== report.data.manifest_hash || !report.data.activation_ready || approve.isPending || report.data.status === "approved" || report.data.status === "active"} onClick={() => approve.mutate()}>{approve.isPending ? "Recording release approval…" : "Approve this release manifest"}</button>
      <TaxonomyError error={approve.error} />{approve.isSuccess && <p role="status">Release approval recorded for the displayed manifest.</p>}
    </section>}
    <section className="textbook-panel"><h2>Legacy crosswalk</h2><TaxonomyError error={crosswalk.error} />{crosswalk.isFetching && <p role="status">Loading reviewed mappings…</p>}
      {crosswalk.data?.length === 0 && <p>No mappings have been proposed. Legacy records remain preserved.</p>}
      <TaxonomyError error={approveMapping.error} />
      {crosswalk.data && crosswalk.data.length > 0 && <div className="textbook-table-wrap"><table><thead><tr><th>Predecessor</th><th>New concept</th><th>Relationship</th><th>Review and evidence</th></tr></thead><tbody>{crosswalk.data.map(mapping => <tr key={mapping.id}><td>{mapping.old_node_id}</td><td>{mapping.new_node_id ?? "Unresolved"}</td><td>{mapping.relation}</td><td>{mapping.reviewed_at ? `Reviewed ${mapping.reviewed_at}` : "Review pending"}<p>{mapping.evidence}</p>{!mapping.reviewed_at && <button type="button" className="textbook-action" disabled={approveMapping.isPending} onClick={() => approveMapping.mutate(mapping.id)}>Approve reviewed mapping</button>}</td></tr>)}</tbody></table></div>}
    </section>
  </div>;
}
