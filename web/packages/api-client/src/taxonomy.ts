import { apiRequest } from "./client";

/** Phase 3 source/review contracts. Taxonomy version and target attempt remain distinct. */
export interface TaxonomyVersion {
  version_id: string;
  taxonomy_version_id: number;
  target_attempt: string;
  status: string;
  manifest_hash: string;
  approved_by: number | null;
  activated_at: string | null;
}
export interface TextbookSpan {
  artifact_id: string;
  pdf_page_start: number;
  pdf_page_end: number;
  review_status: string;
}
export interface TextbookSource extends TextbookSpan {
  edition: string;
  applicable_attempts: string[];
  download_url: string;
  landing_url: string;
  fallback: boolean;
  target_applicability: string;
  availability: string;
  instrument: string | null;
}
export interface TextbookArtifact {
  id: string;
  paper_id: string;
  course_level: string;
  edition: string;
  applicable_attempts: string[];
  landing_url: string;
  download_url: string;
  sha256: string | null;
  retrieved_at: string;
  page_count: number | null;
  edition_evidence: string[];
  availability: string;
  fallback: boolean;
  target_applicability: string;
  expected_structure: { kind: string; module: string | null; chapter: string | null; name: string; download_url: string }[];
  heading_reconciliation: { status: string; expected_count: number; accounted_count: number; unresolved: string[] };
  instrument: string | null;
  extracted_headings?: { number: string; title: string; pdf_page: number }[];
  retrieval_error?: string;
}
export interface TextbookNode {
  id: string;
  paper_id: string;
  parent_id: string | null;
  level: string;
  name: string;
  seq: number;
  heading_origin?: string;
  source_review_status: string;
  descriptor_revision: number | null;
  descriptor_approved: boolean;
  eligible: boolean;
  status?: 'not_started' | 'in_progress' | 'done' | null;
  breadcrumbs: { id: string; name: string; level: string }[];
  sources: TextbookSource[];
  children: TextbookNode[];
}
export interface TextbookDescriptor {
  revision: number;
  definition: string;
  terminology: string[];
  instrument_references?: string[];
  edition?: string | null;
  source_ambiguities?: string[];
  inclusion: string[];
  exclusion: string[];
  nearby_distinctions: string[];
  approved: boolean;
  source_spans: TextbookSpan[];
}
export interface TaxonomyHistory {
  node_id: string;
  records: {
    node_id: string;
    name: string;
    relation: string;
    progress: { status: string; first_done_at: string | null; last_revised_at: string | null } | null;
    note: { body: string; updated_at: string } | null;
  }[];
}
export interface TaxonomyCrosswalk {
  id: number;
  old_node_id: string;
  new_node_id: string | null;
  relation: string;
  evidence: string;
  reviewed_by: number | null;
  reviewed_at: string | null;
}
export interface TaxonomyReleaseReport {
  version_id: string;
  manifest_hash: string;
  status: string;
  node_count: number;
  eligible_count: number;
  source_count: number;
  unresolved_sources: string[];
  unreviewed_descriptors: string[];
  activation_ready: boolean;
  blockers: string[];
  legacy_progress_count: number | null;
  legacy_note_count: number | null;
}
export interface QuestionSourceArtifact {
  id: string;
  source_family: "model" | "mock" | "rtp" | "past_exam" | "case_study";
  course_level: "Final" | "Intermediate" | "Foundation";
  attempt_id: string | null;
  scheme_id: string | null;
  paper_id: string | null;
  paper_ids: string[];
  group: string | null;
  series: string | null;
  artifact_role: "question" | "answer" | "question_and_answer" | "announcement";
  paired_artifact_id: string | null;
  availability: "discovered" | "missing" | "inaccessible" | "downloaded" | "verified";
  landing_url: string;
  download_url: string;
  sha256: string | null;
  page_count: number | null;
  classification_queue: "final_metadata_review" | "outside_corpus" | "not_question_artifact";
  retrieved_at: string;
}

const versionPath = (id: string) => `/api/v1/taxonomy/versions/${encodeURIComponent(id)}`;
const nodePath = (id: string) => `/api/v1/taxonomy/nodes/${encodeURIComponent(id)}`;
export const taxonomyApi = {
  versions: () => apiRequest<TaxonomyVersion[]>("/api/v1/taxonomy/versions"),
  tree: (id: string) => apiRequest<TextbookNode[]>(`${versionPath(id)}/tree`),
  descriptor: (node: string, version: string) => apiRequest<TextbookDescriptor | null>(`${nodePath(node)}/descriptor?version_id=${encodeURIComponent(version)}`),
  approveDescriptor: (node: string, version: string, revision: number) => apiRequest(`${nodePath(node)}/descriptor/approve`, { method: "POST", body: JSON.stringify({ version_id: version, revision }) }),
  approveSource: (node: string, version: string) => apiRequest(`${nodePath(node)}/source/approve`, { method: "POST", body: JSON.stringify({ version_id: version }) }),
  editDescriptor: (node: string, version: string, content: Omit<TextbookDescriptor, "revision" | "approved">) => apiRequest(`${nodePath(node)}/descriptor`, { method: "PUT", body: JSON.stringify({ version_id: version, ...content }) }),
  history: (node: string, version: string) => apiRequest<TaxonomyHistory>(`${nodePath(node)}/history?version_id=${encodeURIComponent(version)}`),
  crosswalk: (id: string) => apiRequest<TaxonomyCrosswalk[]>(`${versionPath(id)}/crosswalk`),
  approveCrosswalk: (id: number, version: string) => apiRequest(`/api/v1/taxonomy/crosswalk/${id}/approve`, { method: "POST", body: JSON.stringify({ version_id: version }) }),
  sources: (id: string) => apiRequest<TextbookArtifact[]>(`${versionPath(id)}/sources`),
  questionSources: (id: string) => apiRequest<QuestionSourceArtifact[]>(`${versionPath(id)}/question-sources`),
  report: (id: string) => apiRequest<TaxonomyReleaseReport>(`${versionPath(id)}/report`),
  approve: (id: string, manifest_hash: string) => apiRequest(`${versionPath(id)}/approve`, { method: "POST", body: JSON.stringify({ manifest_hash }) }),
};
