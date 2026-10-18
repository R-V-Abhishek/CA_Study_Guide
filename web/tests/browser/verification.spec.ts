import { test, expect } from './fixtures';
import type { components } from '../../packages/api-client/src/generated';
type Fixture = { paper_id: string; nodes: { id: string; name: string }[] };
test.beforeEach(async ({ request }) => {
  const response = await request.post('/__test/reset'); expect(response.ok()).toBe(true);
  expect(await response.json()).toEqual({ reset: true }); await request.post('/__test/login');
});
test('Today displays measured zero progress and server plan names without fabricated metrics', async ({ page, request }) => {
  const original: components['schemas']['Dashboard'] = await (await request.get('/api/v1/dashboard')).json();
  await page.route('**/api/v1/dashboard', route => route.fulfill({ json: { ...original, done_subtopics: 0, overall_progress_pct: 0 } }));
  const plan: components['schemas']['StudyPlan'] = await (await request.get('/api/v1/plan')).json();
  await page.goto('/'); await expect(page.getByText(`0 / ${original.total_subtopics} topics completed`, { exact: true })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: 'Personal syllabus progress' })).toHaveAttribute('value', '0');
  await expect(page.getByRole('heading', { name: plan.items[0].node_name, exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Weak topics', exact: true })).toHaveCount(0);
  await expect(page.getByText('Average importance', { exact: false })).toHaveCount(0);
});
test('overview and plan return links retain their URL selections', async ({ page, request }) => {
  const fixture: Fixture = await (await request.get('/__test/fixture')).json();
  await page.goto('/papers?group=1&sort=coverage_asc');
  await page.locator('article').filter({ hasText: 'Financial Reporting' }).getByRole('link', { name: 'Open syllabus' }).click();
  await expect(page).toHaveURL(/syllabus\?paper=/);
  await page.goBack(); await expect(page.getByLabel('Group', { exact: true })).toHaveValue('1');
  await expect(page.getByLabel('Sort', { exact: true })).toHaveValue('coverage_asc');
  await page.goto(`/plan?hours=2&group=1&paper=${fixture.paper_id}`);
  await page.locator('ol a').first().click();
  await page.getByRole('link', { name: '← Return', exact: true }).click();
  await page.getByText('Adjust plan', { exact: true }).click();
  await expect(page.getByLabel('Hours per week')).toHaveValue('2');
  await expect(page.getByLabel('Group', { exact: true })).toHaveValue('1');
  await expect(page.getByLabel('Paper', { exact: true })).toHaveValue(fixture.paper_id);
  await page.getByLabel('Group', { exact: true }).selectOption('2');
  await expect(page.getByLabel('Paper', { exact: true })).toHaveValue('all');
  await expect(page.getByLabel('Paper', { exact: true }).locator(`option[value="${fixture.paper_id}"]`)).toHaveCount(0);
});
test('code-resolution bookmarks and status-filtered progress open the corresponding syllabus', async ({ page, request }) => {
  const fixture: Fixture = await (await request.get('/__test/fixture')).json();
  await page.goto('/papers/P1'); await expect(page).toHaveURL(/syllabus\?paper=P1/);
  await expect(page.getByRole('treeitem').first()).toBeVisible();
  await page.getByRole('button', { name: 'Expand to topics' }).click();
  await expect(page.getByRole('treeitem').filter({ hasText: fixture.nodes[0].name })).toBeVisible();
  await page.goto('/progress?status=done'); await expect(page.getByLabel('Status', { exact: true })).toHaveValue('done');
  await page.locator('.study-row').filter({ hasText: 'Financial Reporting' }).getByRole('link', { name: 'View done topics' }).click();
  await expect(page).toHaveURL(/status=done/); await expect(page.getByLabel('Status', { exact: true })).toHaveValue('done');
  await page.reload(); await expect(page.getByLabel('Status', { exact: true })).toHaveValue('done');
});
test('historical explanation preserves recorded importance and explicitly unavailable configuration', async ({ page, request }) => {
  const fixture: Fixture = await (await request.get('/__test/fixture')).json(); const id = fixture.nodes[0].id;
  const original: components['schemas']['ScoreExplanation'] = await (await request.get(`/api/v1/why/subtopic/${id}`)).json();
  const why: components['schemas']['ScoreExplanation'] = { ...original, explanation_status: 'historical_configuration_unavailable', error: 'Historical configuration unavailable.', configuration_source: null,
    importance_breakdown: { importance: .75, weights: null, exam: null, practice: null, weightage_prior: null }, appearances: [], frequency: null, weightage_section: null };
  await page.route(`**/api/v1/why/subtopic/${id}`, route => route.fulfill({ json: why }));
  await page.goto(`/papers/${fixture.paper_id}/${id}?tab=importance`);
  await expect(page.getByText('Importance: 75.0 / 100', { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/bound historical configuration is unavailable/)).toBeVisible();
  await expect(page.getByRole('table')).toContainText('Unavailable');
  await expect(page.getByText('Formula:', { exact: false })).toHaveCount(0);
});
test('network failures remain errors on every live student page', async ({ page, request }) => {
  const fixture: Fixture = await (await request.get('/__test/fixture')).json();
  await page.route('**/api/v1/**', route => new URL(route.request().url()).pathname === '/api/v1/me' ? route.continue() : route.abort('failed'));
  for (const route of ['/', '/papers', '/plan', '/revision', '/progress', '/mock', `/papers/${fixture.paper_id}`]) {
    await page.goto(route); await expect(page.getByRole('alert').first()).toContainText('Unable to load');
    await expect(page.getByRole('link', { name: 'Today', exact: true })).toBeVisible();
    await expect(page.getByText('Demo Mode', { exact: true })).toHaveCount(0);
  }
});
test('route boundary leaves navigation and retry controls usable', async ({ page, request }) => {
  const dashboard: components['schemas']['Dashboard'] = await (await request.get('/api/v1/dashboard')).json();
  await page.route('**/api/v1/dashboard', route => route.fulfill({ json: { ...dashboard, recent_activity: null } }));
  await page.goto('/'); await expect(page.getByRole('alert')).toContainText('This page could not render.');
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reload', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Plan', exact: true }).click();
  await expect(page.locator('ol li')).toHaveCount(2); await expect(page.getByRole('alert')).toHaveCount(0);
});
test('production diagnostics expose the embedded build identity without private query data', async ({ page }) => {
  await page.goto('/plan?notes=PRIVATE_NOTES&token=PRIVATE_TOKEN');
  await page.locator('.workspace-sidebar .account-menu > summary').click();
  await page.locator('.workspace-sidebar summary').filter({ hasText: 'Technical details' }).click();
  await page.getByRole('button', { name: 'Diagnostics', exact: true }).click();
  await expect(page.locator('pre')).toContainText('browser-harness');
  const info = JSON.parse(await page.locator('pre').innerText());
  expect(info.frontend_revision).toMatch(/^[a-f0-9]{7,12}-[a-f0-9]{12}$/);
  expect(info.frontend_build).toBe(info.frontend_revision); expect(info.api_version).toBe('v1');
  expect(info.score_run.version).toBeTruthy(); expect(info.route).toBe('/plan');
  expect(JSON.stringify(info)).not.toMatch(/PRIVATE_NOTES|PRIVATE_TOKEN/);
});
