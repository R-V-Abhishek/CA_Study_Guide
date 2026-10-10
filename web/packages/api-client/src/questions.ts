import { apiRequest } from './client';
import type { ExtractedQuestion } from './extraction';
import type { PartMapping } from './classification';

export interface CoveredSubtopic {
  node_id: string;
  name: string;
  path: { id: string; name: string; level: string }[];
}
export interface PublishedSource {
  id: number; sha256: string; title: string | null; doc_type_id: string | null;
  attempt_id: string | null; page_count: number | null; url: string; page_url: string;
}
export interface PublishedAsset {
  id: string; source_id: number; page: number; kind: string;
  bbox: number[] | null; concerns: string[]; url: string;
}
export interface PublishedQuestion {
  question_id: string; snapshot_id: number; classification_revision_id: number;
  extraction_revision_id: number; taxonomy_version_id: number; publication_generation: number;
  content: ExtractedQuestion; mappings: PartMapping[]; covered_subtopics: CoveredSubtopic[];
  marks: {
    whole_question_marks: number | null; offered_marks: number | null; selectable_marks: number | null;
    allocations: { part_id: string; marks: number | null; allocation_status: 'reviewed' | 'ambiguous'; choice_group: string | null; node_shares: { node_id: string; share: number; attributed_marks: number | null }[] }[];
    issues: string[];
  };
  sources: PublishedSource[]; assets: PublishedAsset[]; verification_count: number; open_disputes: number;
  extraction_quality: Record<string, unknown>;
  occurrence: { id: number; identity_status: string; signal_class: string } | null;
}
export interface PublishedQuestionSummary {
  question_id: string; snapshot_id: number; paper_id: string; attempt_id: string | null;
  display_label: string; question_text: string; common_stem: string;
  answer_status: string; source_family: string; covered_subtopics: CoveredSubtopic[];
  marks?: PublishedQuestion['marks'] | null;
  matched_parts?: { id: string; label: string }[];
}
export interface QuestionPage {
  items: PublishedQuestionSummary[]; total: number; page: number; page_size: number;
  notes?: { node_id: string; content: string }[];
}
export interface AppearanceQuestion {
  appearance_id: number; question_id: string | null; part_id: string | null;
  provenance_limitation?: string | null;
}
export const questionsApi = {
  question: (id: string) => apiRequest<PublishedQuestion>(`/api/v1/questions/${encodeURIComponent(id)}`),
  questions: (filters: URLSearchParams) => apiRequest<QuestionPage>(`/api/v1/questions?${filters}`),
  search: (filters: URLSearchParams) => apiRequest<QuestionPage>(`/api/v1/search?${filters}`),
  appearance: (id: number) => apiRequest<AppearanceQuestion>(`/api/v1/appearances/${id}`),
};
