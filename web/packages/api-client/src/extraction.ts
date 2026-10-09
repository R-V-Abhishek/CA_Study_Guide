import { apiRequest, ApiError } from "./client";
import { authenticatedFetch } from "./auth";
import type { components } from "./generated";

export interface ExtractionPage<T> { items: T[]; total: number; page: number; page_size: number }
export type ExtractionDocument = components["schemas"]["ExtractionDocument"];
export type ExtractionSpan = components["schemas"]["SourceSpanV1"];
export type ExtractionQuestionPart = components["schemas"]["QuestionPartV1"];
export type ExtractionAnswerPart = components["schemas"]["AnswerPartV1"];
/** Narrow the JSON collections to the shapes emitted by whole-question assembly. */
export interface AnswerPairingCandidate {
  answer_doc_id: number | null; label_path: string; answer_text: string | null;
  page_start: number | null; page_end: number | null;
  block_start: string | null; block_end: string | null; mcq_correct_option: string | null;
}
export type ExtractedQuestion = Omit<components["schemas"]["ExtractedQuestion"], "choices" | "mcq" | "pairing_candidates"> & {
  choices: { label: string; role: string; or_group: string | null; marks: number | null }[];
  mcq: { part_id: string; options: string[]; key: string | null }[];
  pairing_candidates?: { part_id: string; label_path: string; status: string; candidates: AnswerPairingCandidate[] }[];
};
export type ExtractionRevisionSummary = Omit<components["schemas"]["RevisionSummary"], "quality"> & {
  quality: ExtractionQuality;
};
export type ExtractionRevision = Omit<components["schemas"]["RevisionDetail"], "quality" | "questions" | "source_documents"> & {
  quality: ExtractionQuality;
  questions: ExtractedQuestion[];
  source_documents: { id: number; sha256: string; page_count: number | null }[];
};
export interface ExtractionQuality {
  metadata?: string; questions?: string; answers?: string; pairing?: string; ordering?: string;
  marks_choices?: string; readability?: string; human_review?: string; outcome?: string;
  issues: { code: string; severity: string; message: string }[];
}
export type ExtractionPair = components["schemas"]["PairResult"];
export type ExtractionReconciliation = components["schemas"]["ReconciliationResult"];
export type ExtractionCorrection = components["schemas"]["CorrectionRequest"];
export type ExtractionBlock = components["schemas"]["BlockResult"];
export type ExtractionAsset = components["schemas"]["AssetResult"];
export type ExtractionReview = components["schemas"]["ReviewResult"];
const base = "/api/v1/extraction";
async function sourceBlob(url: string, label: string): Promise<Blob> {
  const response = await authenticatedFetch(url);
  if (!response.ok) {
    const payload: { detail?: string } = await response.json().catch(() => ({}));
    throw new ApiError(`${label} unavailable (${response.status})${payload.detail ? `: ${payload.detail}` : ""}`, response.status);
  }
  return response.blob();
}
export const extractionApi = {
  confirmMetadata: (document: number, metadata: components["schemas"]["DocumentConfirmRequest"]) => apiRequest(`/api/v1/curate/documents/${document}/confirm`, { method: "POST", body: JSON.stringify(metadata) }),
  documents: (page: number) => apiRequest<ExtractionPage<ExtractionDocument>>(`${base}/documents?page=${page}&page_size=20`),
  revisions: (document: number, page = 1) => apiRequest<ExtractionPage<ExtractionRevisionSummary>>(`${base}/documents/${document}/revisions?page=${page}&page_size=20`),
  revision: (revision: number) => apiRequest<ExtractionRevision>(`${base}/revisions/${revision}`),
  questions: (revision: number, page: number) => apiRequest<ExtractionPage<ExtractedQuestion>>(`${base}/revisions/${revision}/questions?page=${page}&page_size=10`),
  pairs: (document: number, page: number) => apiRequest<ExtractionPage<ExtractionPair>>(`${base}/documents/${document}/pairs?page=${page}&page_size=10`),
  pair: (document: number, answer_document_id: number, evidence: string) => apiRequest<ExtractionPair>(`${base}/documents/${document}/pairs`, { method: "POST", body: JSON.stringify({ answer_document_id, evidence }) }),
  rejectPair: (pair: number) => apiRequest<ExtractionPair>(`${base}/pairs/${pair}`, { method: "DELETE" }),
  reconciliation: (revision: number, page: number) => apiRequest<ExtractionPage<ExtractionReconciliation>>(`${base}/revisions/${revision}/reconciliation?page=${page}&page_size=10`),
  blocks: (revision: number, page: number) => apiRequest<ExtractionPage<ExtractionBlock>>(`${base}/revisions/${revision}/blocks?page=${page}&page_size=10`),
  assets: (revision: number, page: number) => apiRequest<ExtractionPage<ExtractionAsset>>(`${base}/revisions/${revision}/assets?page=${page}&page_size=10`),
  reviews: (revision: number, page: number) => apiRequest<ExtractionPage<ExtractionReview>>(`${base}/revisions/${revision}/reviews?page=${page}&page_size=10`),
  correct: (revision: number, correction: ExtractionCorrection) => apiRequest<ExtractionRevisionSummary>(`${base}/revisions/${revision}/corrections`, { method: "POST", body: JSON.stringify(correction) }),
  review: (revision: number, dimension: string, status: string, note: string) => apiRequest(`${base}/revisions/${revision}/reviews`, { method: "POST", body: JSON.stringify({ dimension, status, note }) }),
  promote: (revision: number, expected_current_revision_id: number | null) => apiRequest(`${base}/revisions/${revision}/promote`, { method: "POST", body: JSON.stringify({ expected_current_revision_id }) }),
  pdf: (document: number) => sourceBlob(`${base}/documents/${document}/pdf`, "Source PDF"),
  page: (document: number, page: number) => sourceBlob(`${base}/documents/${document}/pages/${page}`, "Source page"),
  asset: (asset: number) => sourceBlob(`${base}/assets/${asset}/image`, "Source asset"),
};
