import type { PublishedQuestion, PublishedQuestionSummary } from '@caf/api-client';

const span = { contract_version: 'shared-study.v1' as const, document_sha256: 'demo-source-sha256', page_start: 1, page_end: 1, block_start: null, block_end: null, official_url: null };
export const demoQuestion: PublishedQuestion = {
  question_id: 'demo.whole-question', snapshot_id: 1, classification_revision_id: 1, extraction_revision_id: 1, taxonomy_version_id: 1, publication_generation: 1,
  content: {
    contract_version: 'shared-study.v1', question_id: 'demo.whole-question', content_revision: 'demo', paper_id: 'demo.P1', source_attempt_id: null,
    display_label: 'Demo complete question', common_stem: 'A company enters into a lease. Both parts use this shared case.', question_text: 'Consider the following independent requirements.',
    parts: [{ contract_version: 'shared-study.v1', id: 'demo.part-a', label: '(a)', label_path: '1(a)', sequence: 1, question_text: 'Explain the classification of the lease.', marks: 4, source_spans: [span], parts: [] }, { contract_version: 'shared-study.v1', id: 'demo.part-b', label: '(b)', label_path: '1(b)', sequence: 2, question_text: 'Describe the relevant disclosures.', marks: null, source_spans: [span], parts: [] }],
    answers: [{ contract_version: 'shared-study.v1', id: 'demo.answer-a', question_part_id: 'demo.part-a', sequence: 1, answer_text: 'This is a synthetic demo answer. Assess the substance of the lease and the applicable classification criteria.', source_spans: [span], parts: [] }],
    answer_status: 'partial', source_spans: [span], label_path: '1', course_level: 'final', scheme_id: 'demo', source_family: 'practice', source_collection_id: 'demo.undated', question_status: 'complete', readability_status: 'passed', pairing_status: 'partial', review_status: 'reviewed', choices: [], mcq: [], assets: [], source_document_ids: [1], pairing_candidates: [],
  },
  mappings: [], covered_subtopics: [{ node_id: 'P1-EQ3KR1', name: 'Lease classification', path: [{ id: 'P1', name: 'Financial Reporting', level: 'paper' }, { id: 'P1-EQ3KR1', name: 'Lease classification', level: 'subtopic' }] }],
  marks: { whole_question_marks: null, offered_marks: null, selectable_marks: null, allocations: [{ part_id: 'demo.part-a', marks: 4, allocation_status: 'reviewed', choice_group: null, node_shares: [{ node_id: 'P1-EQ3KR1', share: 1, attributed_marks: 4 }] }], issues: ['Part (b) marks are unknown.'] },
  sources: [{ id: 1, sha256: span.document_sha256, title: 'Synthetic demo collection', doc_type_id: 'DEMO', attempt_id: null, page_count: 1, url: '/api/v1/published-sources/1', page_url: '/api/v1/published-sources/1/pages/{page}' }], assets: [], verification_count: 0, open_disputes: 0, extraction_quality: { outcome: 'demo' }, occurrence: null,
};
export const demoQuestionSummary: PublishedQuestionSummary = { question_id: demoQuestion.question_id, snapshot_id: 1, paper_id: 'demo.P1', attempt_id: null, display_label: demoQuestion.content.display_label, question_text: demoQuestion.content.question_text, common_stem: demoQuestion.content.common_stem, answer_status: demoQuestion.content.answer_status, source_family: 'practice', covered_subtopics: demoQuestion.covered_subtopics };
