import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import type { components } from '../../packages/api-client/src/generated';

type Fixture = { paper_id: string; nodes: { id: string; name: string }[]; score_run_id: number };
type StudyPlan = components['schemas']['StudyPlan'];
type PaperSummary = components['schemas']['PaperSummary'];
type PaperTree = components['schemas']['PaperTree'];
const paper: PaperSummary = { id: 'synthetic.paper', code: 'P1', name: 'Real returned paper name', group_no: 1, total_subtopics: 2, completed_subtopics: 0, raw_progress_pct: 0, weighted_coverage_pct: 0, average_importance: null, revision_due_count: 0, weak_topic_count: 1 };
const plan: StudyPlan = { hours_per_week: 2, minutes_per_subtopic: 45, budget_items: 2, total_allocated: 2, items: [
  { node_id: 'synthetic.b', node_name: 'Returned beta topic', paper_id: paper.id, paper_code: paper.code, chapter_id: 'chapter', chapter_name: 'Chapter', status: 'not_started', importance: .5, priority_score: .5, weak: false, freq_hits: 0, freq_window: 0, exam_marks_total: 0, reason: 'Recorded reason' },
  { node_id: 'synthetic.a', node_name: 'Returned alpha topic', paper_id: paper.id, paper_code: paper.code, chapter_id: 'chapter', chapter_name: 'Chapter', status: 'not_started', importance: .5, priority_score: .5, weak: true, freq_hits: 3, freq_window: 5, exam_marks_total: 7.5, reason: 'Recorded reason' },
] };
const tree: PaperTree = { paper_id: paper.id, code: paper.code, name: paper.name, chapters: [{ id: 'chapter', name: 'Returned chapter', seq: 1, total_subtopics: 2, completed_subtopics: 0, progress_pct: 0, weightage_min_pct: null, weightage_max_pct: null, weightage_section_name: null, topics: [{ id: 'topic', name: 'Returned parent topic', seq: 1, subtopics: plan.items.map((item, index) => ({ id: item.node_id, name: item.node_name, seq: 1, status: index === 0 ? 'in_progress' : 'not_started', notes: null, first_done_at: null, last_revised_at: null, importance: .5, freq_hits: item.freq_hits, freq_window: 5, weak: item.weak, applicable: true })) }] }] };
async function fixture(request: APIRequestContext): Promise<Fixture> { return (await request.get('/__test/fixture')).json(); }
async function controlledPapers(page: Page) {
  await page.route('**/api/v1/papers', route => route.fulfill({ json: [paper] }));
  await page.route(`**/api/v1/papers/${paper.id}/tree`, route => route.fulfill({ json: tree }));
}
test.beforeEach(async ({ request }) => { await request.post('/__test/reset'); });

test('plan direct loading, refresh and returned names and destinations', async ({ page }) => {
  await controlledPapers(page);
  let requests = 0;
  await page.route('**/api/v1/plan*', async route => { requests++; await new Promise(resolve => setTimeout(resolve, 350)); await route.fulfill({ json: plan }); });
  await page.goto('/plan');
  await expect(page.getByRole('status')).toContainText('Loading');
  await expect(page.getByRole('heading', { name: 'Weekly Study Plan' })).toBeVisible();
  await expect(page.getByLabel('Hours per week')).toHaveValue('2');
  await expect(page.getByRole('link', { name: '1. Returned beta topic' })).toHaveAttribute('href', `/papers/${paper.id}/synthetic.b`);
  await expect(page.getByText('Recorded reason').first()).toBeVisible();
  await page.getByRole('button', { name: 'Refresh plan' }).click();
  await expect.poll(() => requests).toBe(2);
});

test('plan empty, failed and invalid budgets remain honest', async ({ page }) => {
  await controlledPapers(page);
  await page.route('**/api/v1/plan*', route => route.fulfill({ json: { ...plan, total_allocated: 0, items: [] } }));
  await page.goto('/plan?hours=0.1');
  await expect(page.getByText('No topics allocated for this budget and selection.')).toBeVisible();
  await page.unroute('**/api/v1/plan*');
  await page.route('**/api/v1/plan*', route => route.fulfill({ status: 503, json: { detail: 'Plan unavailable' } }));
  await page.getByRole('button', { name: 'Refresh plan' }).click();
  await expect(page.getByRole('alert')).toContainText('Plan unavailable');
  await expect(page.getByText('Returned beta topic')).toHaveCount(0);
  await page.goto('/plan?hours=NaN&group=3');
  await expect(page.getByRole('alert')).toContainText('finite positive hours');
});

test('paper zero values, unavailable scores and URL sorting survive reload', async ({ page }) => {
  await controlledPapers(page);
  await page.goto('/papers');
  await expect(page.getByText('Weighted coverage: 0.0%')).toBeVisible();
  await expect(page.getByText('Average importance: Unavailable')).toBeVisible();
  await expect(page.getByRole('link', { name: /Real returned paper name/ })).toHaveAttribute('href', `/papers/${paper.id}`);
  await page.getByLabel('Group', { exact: true }).selectOption('2');
  await expect(page.getByText('No results match these filters.')).toBeVisible();
  await expect(page).toHaveURL(/group=2/);
  await page.reload();
  await expect(page.getByLabel('Group', { exact: true })).toHaveValue('2');
  await page.goBack();
  await expect(page.getByLabel('Group', { exact: true })).toHaveValue('all');
});

test('paper combined filters, stable ties and return navigation retain URL', async ({ page }) => {
  await controlledPapers(page);
  const originalErrors: string[] = []; page.on('pageerror', error => originalErrors.push(error.message));
  await page.goto(`/papers/${paper.id}`);
  await expect(page.locator('a.topic-link').filter({ hasText: /Returned (alpha|beta) topic/ }).first()).toHaveText('Returned alpha topic');
  await page.getByLabel('Search', { exact: true }).fill('Returned');
  await page.getByLabel('Status', { exact: true }).selectOption('in_progress');
  await page.getByLabel('Weak only').check();
  await expect(page.getByText('No results match these filters.')).toBeVisible();
  await page.getByLabel('Status', { exact: true }).selectOption('not_started');
  await expect(page.getByRole('link', { name: 'Returned alpha topic' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Returned beta topic' })).toHaveCount(0);
  await page.getByRole('link', { name: 'Returned alpha topic' }).click();
  await page.getByRole('link', { name: '← Return', exact: true }).click();
  await expect(page.getByLabel('Search', { exact: true })).toHaveValue('Returned');
  await expect(page.getByLabel('Status', { exact: true })).toHaveValue('not_started');
  await expect(page.getByLabel('Weak only')).toBeChecked();
  await page.reload();
  await expect(page.getByLabel('Weak only')).toBeChecked();
  expect(originalErrors).toEqual([]);
});

test('coverage exposes failed paper loads rather than complete totals', async ({ page }) => {
  await controlledPapers(page);
  await page.unroute(`**/api/v1/papers/${paper.id}/tree`);
  await page.route(`**/api/v1/papers/${paper.id}/tree`, route => route.fulfill({ status: 503, json: { detail: 'Tree unavailable' } }));
  await page.goto('/progress');
  await expect(page.getByText('Coverage is incomplete because some papers failed to load. Complete totals are unavailable.')).toBeVisible();
  await expect(page.getByRole('alert').filter({ hasText: 'Tree unavailable' })).toBeVisible();
  await expect(page.getByText('0 / 2 topics completed')).toHaveCount(0);
});

test('integration plan honors settings, navigation and small budgets', async ({ page, request }) => {
  const data = await fixture(request);
  await page.goto('/');
  await page.getByRole('link', { name: 'Study Plan', exact: true }).click();
  await expect(page.getByLabel('Hours per week')).toHaveValue('2');
  await expect(page.locator('ol li')).toHaveCount(2);
  await expect(page.locator('ol a').first()).toContainText(data.nodes[0].name);
  await page.getByLabel('Hours per week').fill('0.1');
  await expect(page.getByText('No topics allocated for this budget and selection.')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Hours per week')).toHaveValue('0.1');
});

test('integration failed progress rolls back and note failure retains edits', async ({ page, request }) => {
  const data = await fixture(request); const id = data.nodes[0].id;
  await page.route(`**/api/v1/subtopics/${id}/progress`, route => route.fulfill({ status: 500, json: { detail: 'Progress rejected' } }));
  await page.route(`**/api/v1/subtopics/${id}/notes`, route => route.fulfill({ status: 500, json: { detail: 'Notes rejected' } }));
  await page.goto(`/papers/${data.paper_id}/${id}`);
  await page.getByLabel('Progress', { exact: true }).selectOption('done');
  await expect(page.getByRole('alert')).toContainText('Progress was not saved');
  await expect(page.getByLabel('Progress', { exact: true })).toHaveValue('not_started');
  await expect(page.getByText('Progress saved.', { exact: true })).toHaveCount(0);
  await page.getByLabel('Notes', { exact: true }).fill('Retain this unsaved text');
  await expect(page.getByRole('status').filter({ hasText: 'Failed to save' })).toBeVisible();
  await expect(page.getByLabel('Notes', { exact: true })).toHaveValue('Retain this unsaved text');
  expect((await (await request.get(`/api/v1/subtopics/${id}`)).json()).notes).toBeNull();
});

test('integration successful mutations persist and invalidate paper/dashboard/plan', async ({ page, request }) => {
  const data = await fixture(request); const id = data.nodes[0].id;
  await page.goto('/');
  await expect(page.getByText(/1 \/ \d+ topics completed/)).toBeVisible();
  await page.getByRole('link', { name: 'Papers', exact: true }).click();
  await page.locator(`a[href="/papers/${data.paper_id}"]`).click();
  await page.getByRole('link', { name: data.nodes[0].name, exact: true }).click();
  await page.getByLabel('Progress', { exact: true }).selectOption('done');
  await expect(page.getByText('Progress saved.', { exact: true })).toBeVisible();
  await page.getByLabel('Notes', { exact: true }).fill('Persisted browser note');
  await expect(page.getByRole('status').filter({ hasText: /^Saved$/ })).toBeVisible();
  const response = await (await request.get(`/api/v1/subtopics/${id}`)).json();
  expect(response.status).toBe('done'); expect(response.notes).toBe('Persisted browser note');
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await expect(page.getByText(/2 \/ \d+ topics completed/)).toBeVisible();
  await page.getByRole('link', { name: 'Study Plan', exact: true }).click();
  await expect(page.locator('ol a').filter({ hasText: data.nodes[0].name })).toHaveCount(0);
});

test('integration serialized rapid notes keep latest text across node changes', async ({ page, request }) => {
  const data = await fixture(request); const id = data.nodes[0].id;
  const bodies: string[] = [];
  await page.route(`**/api/v1/subtopics/${id}/notes`, async route => {
    bodies.push(route.request().postDataJSON().notes);
    const response = await route.fetch();
    if (bodies.length === 1) await new Promise(resolve => setTimeout(resolve, 1200));
    await route.fulfill({ response });
  });
  page.on('dialog', dialog => dialog.accept());
  await page.goto(`/papers/${data.paper_id}`);
  await page.getByRole('link', { name: data.nodes[0].name, exact: true }).click();
  await page.getByLabel('Notes', { exact: true }).fill('First edit');
  await expect.poll(() => bodies.length).toBe(1);
  await page.getByLabel('Notes', { exact: true }).fill('Latest edit');
  await page.goBack();
  await expect(page.getByLabel('Search', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: data.nodes[1].name, exact: true }).click();
  await expect(page.getByLabel('Notes', { exact: true })).toHaveValue('');
  await page.getByRole('link', { name: '← Return', exact: true }).click();
  await page.getByRole('link', { name: data.nodes[0].name, exact: true }).click();
  await expect(page.getByLabel('Notes', { exact: true })).toHaveValue('Latest edit');
  await expect.poll(async () => (await (await request.get(`/api/v1/subtopics/${id}`)).json()).notes).toBe('Latest edit');
  await expect(page.getByRole('status').filter({ hasText: /^Saved$/ })).toBeVisible();
});

test('integration failed revisions and mock mutations show no false success', async ({ page, request }) => {
  const data = await fixture(request);
  await page.route('**/api/v1/subtopics/*/revisions', route => route.fulfill({ status: 503, json: { detail: 'Revision rejected' } }));
  await page.goto('/revision');
  await expect(page.getByRole('heading', { name: data.nodes[2].name })).toBeVisible();
  await page.getByRole('button', { name: 'Remembered' }).click();
  await expect(page.getByRole('alert')).toContainText('Revision was not saved');
  await expect(page.getByRole('heading', { name: data.nodes[2].name })).toBeVisible();
  await page.route('**/api/v1/mock-tests', async route => route.request().method() === 'POST' ? route.fulfill({ status: 503, json: { detail: 'Creation rejected' } }) : route.continue());
  await page.goto('/mock');
  await page.getByRole('button', { name: 'Record mock test' }).click();
  await page.getByLabel('Score', { exact: true }).fill('7.5');
  await page.getByRole('button', { name: 'Save mock test' }).click();
  await expect(page.getByRole('alert')).toContainText('Creation failed');
  await expect(page.getByRole('button', { name: 'Save mock test' })).toBeVisible();
  const created = await (await request.post('/api/v1/mock-tests', { data: { paper_id: data.paper_id, score: 7.5, max_score: 100, taken_on: '2026-10-01' } })).json();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.reload();
  await page.route(`**/api/v1/mock-tests/${created.id}`, route => route.fulfill({ status: 503, json: { detail: 'Deletion rejected' } }));
  await page.getByRole('button', { name: 'Delete mock test' }).click();
  await expect(page.getByRole('alert')).toContainText('Deletion failed');
  await expect(page.getByText('7.5 / 100')).toBeVisible();
});

test('integration score explanations use normalized signals and diagnostics identify build', async ({ page, request }) => {
  const data = await fixture(request);
  await page.goto(`/papers/${data.paper_id}/${data.nodes[0].id}`);
  await page.getByRole('button', { name: 'Why this importance?' }).click();
  await expect(page.getByRole('table')).toBeVisible();
  await expect(page.getByText(/Raw exam signal: 7.5/)).toBeVisible();
  await expect(page.getByText('750%', { exact: false })).toHaveCount(0);
  await expect(page.getByText(/exam probability/i)).toHaveCount(0);
  await page.getByRole('button', { name: 'Diagnostics', exact: true }).click();
  await expect(page.locator('pre')).toContainText('browser-harness');
  await expect(page.locator('pre')).toContainText(String(data.score_run_id));
  await expect(page.locator('pre')).toContainText('frontend_revision');
  await expect(page.locator('pre')).not.toContainText('question_text');
});

test('all live and explicit demo routes render without exceptions; demo has no API traffic', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  for (const route of ['/', '/papers', '/plan', '/revision', '/progress', '/mock']) {
    await page.goto(route);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
  }
  const traffic: string[] = []; page.on('request', request => { if (request.url().includes('/api/v1/')) traffic.push(request.url()); });
  await page.goto('/plan?demo=true');
  await expect(page.getByText('Demo Mode', { exact: true })).toBeVisible();
  await expect(page.locator('ol li')).not.toHaveCount(0);
  await page.getByRole('link', { name: 'Papers', exact: true }).click();
  await expect(page).toHaveURL(/demo=true/);
  await page.getByRole('link', { name: /P1 — Financial Reporting/ }).click();
  await page.getByRole('link', { name: 'Classification of Leases into Operating vs Finance', exact: true }).click();
  await page.getByLabel('Progress', { exact: true }).selectOption('done');
  await expect(page.getByText('Progress saved.', { exact: true })).toBeVisible();
  await page.getByLabel('Notes', { exact: true }).fill('Demo local note');
  await expect(page.getByRole('status').filter({ hasText: /^Saved$/ })).toBeVisible();
  await page.getByRole('link', { name: '← Return', exact: true }).click();
  await page.getByRole('link', { name: 'Classification of Leases into Operating vs Finance', exact: true }).click();
  await expect(page.getByLabel('Notes', { exact: true })).toHaveValue('Demo local note');
  for (const name of ['Dashboard', 'Study Plan', 'Revision', 'Coverage', 'Mock Tests']) {
    await page.getByRole('link', { name, exact: true }).click();
    await expect(page).toHaveURL(/demo=true/);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  }
  expect(traffic).toEqual([]); expect(errors).toEqual([]);
});

test('integration revision saves persist and move the queue only after acceptance', async ({ page, request }) => {
  const data = await fixture(request);
  await page.goto('/revision');
  await expect(page.getByRole('heading', { name: data.nodes[2].name })).toBeVisible();
  await page.getByRole('button', { name: 'Remembered' }).click();
  await expect(page.getByText('Revision saved.', { exact: true })).toBeVisible();
  await expect(page.getByText('Revision queue complete.', { exact: true })).toBeVisible();
  expect((await (await request.get('/api/v1/revision/due')).json()).total_due).toBe(0);
  await page.reload();
  await expect(page.getByText('No revisions due.', { exact: true })).toBeVisible();
});

test('integration mock creation/deletion persist and paper URL selection reloads', async ({ page, request }) => {
  const data = await fixture(request);
  await page.goto('/mock');
  await page.getByLabel('Paper filter').selectOption(data.paper_id);
  await page.reload();
  await expect(page.getByLabel('Paper filter')).toHaveValue(data.paper_id);
  await page.getByRole('button', { name: 'Record mock test' }).click();
  await page.getByLabel('Label', { exact: true }).fill('Persisted mock');
  await page.getByLabel('Score', { exact: true }).fill('0');
  await page.getByRole('button', { name: 'Save mock test' }).click();
  await expect(page.getByText('Mock test saved.', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Persisted mock · P1' })).toBeVisible();
  expect((await (await request.get('/api/v1/mock-tests')).json())).toHaveLength(1);
  await page.getByRole('button', { name: 'Delete mock test' }).click();
  await expect(page.getByText('Mock test deleted.', { exact: true })).toBeVisible();
  await expect(page.getByText('No mock tests match this paper.', { exact: true })).toBeVisible();
  expect((await (await request.get('/api/v1/mock-tests')).json())).toHaveLength(0);
});

test('unsaved notes warn on link and browser back; cancel preserves the draft', async ({ page, request }) => {
  const data = await fixture(request);
  const id = data.nodes[0].id;
  await page.route(`**/api/v1/subtopics/${id}/notes`, route => route.fulfill({ status: 503, json: { detail: 'Keep draft unsaved' } }));
  await page.goto(`/papers/${data.paper_id}`);
  await page.getByRole('link', { name: data.nodes[0].name, exact: true }).click();
  await page.getByLabel('Notes', { exact: true }).fill('Preserve this draft');
  const canceled = page.waitForEvent('dialog').then(async dialog => {
    expect(dialog.message()).toContain('unsaved notes');
    await dialog.dismiss();
  });
  await page.getByRole('link', { name: '← Return', exact: true }).click();
  await canceled;
  await expect(page.getByLabel('Notes', { exact: true })).toHaveValue('Preserve this draft');
  await expect(page).toHaveURL(new RegExp(`${id}$`));
  const accepted = page.waitForEvent('dialog').then(async dialog => {
    expect(dialog.message()).toContain('unsaved notes');
    await dialog.accept();
  });
  await page.goBack();
  await accepted;
  await expect(page.getByLabel('Search', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: data.nodes[0].name, exact: true }).click();
  await expect(page.getByLabel('Notes', { exact: true })).toHaveValue('Preserve this draft');
});
