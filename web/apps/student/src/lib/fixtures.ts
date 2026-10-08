import planFixture from '../fixtures/plan.json';
import papersFixture from '../fixtures/papers.json';
import dashboardFixture from '../fixtures/dashboard.json';
import revisionFixture from '../fixtures/revision.json';
import { demoQuestion, demoQuestionSummary } from '../fixtures/question';
import type { PlanData, PaperSummary, DashboardData, RevisionData, PaperTree, SubtopicData, MockTest, WhyData, MetaData } from './contracts';
type Status = 'not_started' | 'in_progress' | 'done';
function status(value: string): Status { if (value === 'not_started' || value === 'in_progress' || value === 'done') return value; throw new Error('Invalid demo status'); }
const plan: PlanData = { ...planFixture, basis: 'syllabus', allocated_minutes: planFixture.total_allocated * planFixture.minutes_per_subtopic, unused_minutes: planFixture.hours_per_week * 60 - planFixture.total_allocated * planFixture.minutes_per_subtopic, items: planFixture.items.map(item => ({ ...item, importance: null, priority_score: null, weak: false, reason: 'Syllabus-based demo plan in textbook order.', status: status(item.status) })) };
const papers: PaperSummary[] = papersFixture;
const dashboard: DashboardData = { ...dashboardFixture, weighted_coverage: { ...dashboardFixture.weighted_coverage, basis: 'unweighted' }, plan_preview: plan.items };
const revision: RevisionData = revisionFixture;
const mocks: MockTest[] = [];
const edits = new Map<string, { notes?: string; status?: Status }>();
export function demoUpdate(id: string, values: { notes?: string; status?: Status }) { edits.set(id, { ...edits.get(id), ...values }); }
export function demoRevise(id: string) { revision.items = revision.items.filter(item => item.node_id !== id); revision.total_due = revision.items.length; }
export function demoCreateMock(body: { paper_id: string; label: string; score: number; max_score: number; taken_on: string; notes: string }) { mocks.push({ ...body, id: Date.now(), paper_code: papers.find(p => p.id === body.paper_id)?.code ?? '', score_pct: body.score / body.max_score * 100, attempt_id: null }); }
export function demoDeleteMock(id: number) { const index = mocks.findIndex(test => test.id === id); if (index >= 0) mocks.splice(index, 1); }
function tree(paper: PaperSummary): PaperTree {
  const items = plan.items.filter(item => item.paper_id === paper.id);
  return { paper_id: paper.id, code: paper.code, name: paper.name, chapters: items.length ? [{ id: `${paper.id}.chapter`, name: 'Demo chapter', seq: 1, total_subtopics: items.length, completed_subtopics: items.filter(i => edits.get(i.node_id)?.status === 'done').length, progress_pct: items.filter(i => edits.get(i.node_id)?.status === 'done').length / items.length * 100, weightage_min_pct: null, weightage_max_pct: null, weightage_section_name: null, topics: [{ id: `${paper.id}.topic`, name: 'Demo topic', seq: 1, subtopics: items.map((item, index) => ({ id: item.node_id, name: item.node_name, seq: index, status: edits.get(item.node_id)?.status ?? item.status, notes: edits.get(item.node_id)?.notes ?? null, importance: item.importance, freq_hits: 0, freq_window: 0, weak: false, applicable: true, first_done_at: null, last_revised_at: null })) }] }] : [] };
}
function detail(id: string): SubtopicData {
  const item = plan.items.find(candidate => candidate.node_id === id);
  if (!item) throw new Error('Demo topic unavailable');
  const paper = papers.find(candidate => candidate.id === item.paper_id)!;
  return { id, name: item.node_name, paper: { id: paper.id, code: paper.code, name: paper.name }, chapter: { id: `${paper.id}.chapter`, name: 'Demo chapter' }, topic: { id: `${paper.id}.topic`, name: 'Demo topic' }, status: edits.get(id)?.status ?? item.status, notes: edits.get(id)?.notes ?? '', status_changed_at: null, first_done_at: null, last_revised_at: null, weightage: null, score_run: null, score: { importance: item.importance, exam_score: null, practice_score: null, weight_prior: null, freq_hits: 0, freq_window: 0, exam_marks_total: 0, exam_count: 0, practice_count: 0, first_exam_attempt: null, last_exam_attempt: null, weak: false, applicable: true, applicability_status: 'applicable' }, appearances: [] };
}
export function demoResponse<T>(path: string): T {
  const url = new URL(path, window.location.origin);
  let response: unknown;
  const paperFilter = url.searchParams.get('paper');
  if (url.pathname === '/api/v1/questions' || url.pathname === '/api/v1/search') { const q = url.searchParams.get('q')?.toLowerCase(); const items = [demoQuestionSummary].filter(item => (!q || `${item.common_stem} ${item.question_text} ${item.covered_subtopics.map(node => node.name).join(' ')}`.toLowerCase().includes(q)) && ['paper_id', 'attempt_id', 'source_family', 'answer_status'].every(key => !url.searchParams.get(key) || item[key as keyof typeof item] === url.searchParams.get(key))); response = { items, total: items.length, page: Number(url.searchParams.get('page') ?? 1), page_size: 20, ...(url.searchParams.get('include_notes') === 'true' ? { notes: [...edits].filter(([, edit]) => edit.notes && (!q || edit.notes.toLowerCase().includes(q))).map(([node_id, edit]) => ({ node_id, content: edit.notes })) } : {}) }; }
  else if (url.pathname === '/api/v1/coverage') response = { context: { target_attempt_id: dashboard.target_attempt, taxonomy_version_id: null, readiness: 'demo_inventory_unavailable' }, freshness: { publication_generation: 0, scored_generation: null, computed_at: null, status: 'unavailable' }, items: [] };
  else if (url.pathname.startsWith('/api/v1/questions/')) { if (decodeURIComponent(url.pathname.split('/')[4]) !== demoQuestion.question_id) throw new Error('Demo question unavailable'); response = demoQuestion; }
  else if (url.pathname === '/api/v1/papers') response = papers.map(p => { const data = tree(p); const completed = data.chapters.reduce((sum, ch) => sum + ch.completed_subtopics, 0); return { ...p, completed_subtopics: completed, raw_progress_pct: p.total_subtopics ? completed / p.total_subtopics * 100 : 0, weighted_coverage_pct: null, average_importance: null }; });
  else if (url.pathname === '/api/v1/dashboard') response = { ...dashboard, done_subtopics: [...edits.values()].filter(e => e.status === 'done').length, overall_progress_pct: [...edits.values()].filter(e => e.status === 'done').length / dashboard.total_subtopics * 100, revision_due_count: revision.items.length };
  else if (url.pathname === '/api/v1/plan') { const hours = Number(url.searchParams.get('hours') ?? plan.hours_per_week); const group = url.searchParams.get('group'); const items = plan.items.filter(i => (!paperFilter || i.paper_id === paperFilter || i.paper_code === paperFilter) && (!group || String(papers.find(p => p.id === i.paper_id)?.group_no) === group) && edits.get(i.node_id)?.status !== 'done').sort((a, b) => Number((edits.get(b.node_id)?.status ?? b.status) === 'in_progress') - Number((edits.get(a.node_id)?.status ?? a.status) === 'in_progress') || a.node_id.localeCompare(b.node_id)).slice(0, Math.floor(hours * 60 / plan.minutes_per_subtopic)); response = { ...plan, hours_per_week: hours, budget_items: Math.floor(hours * 60 / plan.minutes_per_subtopic), total_allocated: items.length, allocated_minutes: items.length * plan.minutes_per_subtopic, unused_minutes: Math.max(0, Math.floor(hours * 60) - items.length * plan.minutes_per_subtopic), items }; }
  else if (url.pathname === '/api/v1/revision/due') response = revision;
  else if (url.pathname === '/api/v1/mock-tests') response = mocks.filter(t => !paperFilter || t.paper_id === paperFilter || t.paper_code === paperFilter);
  else if (url.pathname === '/api/v1/tree' || /^\/api\/v1\/papers\/[^/]+\/tree$/.test(url.pathname)) { const id = paperFilter ?? decodeURIComponent(url.pathname.split('/')[4]); const paper = papers.find(p => p.id === id || p.code === id); if (!paper) throw new Error('Demo paper unavailable'); response = tree(paper); }
  else if (url.pathname.startsWith('/api/v1/subtopics/')) response = detail(decodeURIComponent(url.pathname.split('/')[4]));
  else if (url.pathname.startsWith('/api/v1/why/')) { const value: WhyData = { node_id: decodeURIComponent(url.pathname.split('/')[5]), explanation_status: 'no_score_run', error: 'Demo has no score run', score_run: null, configuration_source: null, importance_breakdown: { importance: null, weights: null, exam: null, practice: null, weightage_prior: null }, subtopic: { id: 'demo', name: 'Demo topic', paper: null, chapter: null, topic: null, applicable: true }, frequency: null, weightage_section: null, appearances: [] }; response = value; }
  else if (url.pathname === '/api/v1/meta') { const value: MetaData = { api_version: 'v1', backend_revision: 'demo', taxonomy_version: 'demo', scoring_version: 'demo', target_attempt: dashboard.target_attempt, score_run_id: null, score_run_computed_at: null, score_run: null, ingestion_coverage: [] }; response = value; }
  else throw new Error('Demo endpoint unavailable');
  // Each demo response above is checked against its generated endpoint type.
  return structuredClone(response) as T;
}
