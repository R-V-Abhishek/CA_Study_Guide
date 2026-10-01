import { test, expect } from '@playwright/test';
import type { components } from '../../packages/api-client/src/generated';

type Fixture = { paper_id: string; nodes: { id: string; name: string }[] };
test.beforeEach(async ({ request }) => {
  const response = await request.post('/__test/reset');
  expect(response.ok()).toBe(true);
  expect(await response.json()).toEqual({ reset: true });
});

test('dashboard distinguishes zero coverage from unavailable and uses real plan names', async ({ page, request }) => {
  const original: components['schemas']['Dashboard'] = await (await request.get('/api/v1/dashboard')).json();
  let data: components['schemas']['Dashboard'] = {
    ...original, done_subtopics: 0, overall_progress_pct: 0,
    weighted_coverage: { ...original.weighted_coverage, overall_coverage_pct: 0 },
  };
  await page.route('**/api/v1/dashboard', route => route.fulfill({ json: data }));
  await page.goto('/');
  await expect(page.getByText(/0\.0% completion/)).toBeVisible();
  await expect(page.getByText('Weighted coverage: 0.0%', { exact: true })).toBeVisible();
  const item = data.plan_preview[0];
  await expect(page.getByRole('link', { name: item.node_name, exact: true })).toHaveAttribute('href', `/papers/${item.paper_id}/${item.node_id}`);
  data = { ...data, weighted_coverage: { ...data.weighted_coverage, overall_coverage_pct: null } };
  await page.reload();
  await expect(page.getByText('Weighted coverage: Unavailable', { exact: true })).toBeVisible();
});

test('overview and plan return links retain their URL selections', async ({ page, request }) => {
  const fixture: Fixture = await (await request.get('/__test/fixture')).json();
  await page.goto('/papers?group=1&sort=importance_desc');
  await page.getByRole('link', { name: /P1 — Financial Reporting/ }).click();
  await page.getByRole('link', { name: '← Papers', exact: true }).click();
  await expect(page).toHaveURL(/\/papers\?group=1&sort=importance_desc$/);
  await expect(page.getByLabel('Group', { exact: true })).toHaveValue('1');
  await expect(page.getByLabel('Sort', { exact: true })).toHaveValue('importance_desc');
  await page.goto(`/plan?hours=2&group=1&paper=${fixture.paper_id}`);
  await page.locator('ol a').first().click();
  await page.getByRole('link', { name: '← Return', exact: true }).click();
  await expect(page.getByLabel('Hours per week')).toHaveValue('2');
  await expect(page.getByLabel('Group', { exact: true })).toHaveValue('1');
  await expect(page.getByLabel('Paper', { exact: true })).toHaveValue(fixture.paper_id);
  await page.getByLabel('Group', { exact: true }).selectOption('2');
  await expect(page.getByLabel('Paper', { exact: true })).toHaveValue('all');
  await expect(page.getByLabel('Paper', { exact: true }).locator(`option[value="${fixture.paper_id}"]`)).toHaveCount(0);
});

test('code-resolution navigation and combined coverage filters use actual trees', async ({ page, request }) => {
  const fixture: Fixture = await (await request.get('/__test/fixture')).json();
  const calls: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/')) calls.push(request.url()); });
  await page.goto('/papers/P1');
  await expect(page.getByRole('link', { name: fixture.nodes[0].name, exact: true })).toBeVisible();
  expect(calls.filter(url => url.includes('/tree?paper=P1'))).toHaveLength(1);
  expect(calls.filter(url => url.includes('/papers/s2023.P1/tree'))).toHaveLength(0);
  await page.goto('/progress?status=not_started&weak=true&sort=coverage_asc');
  await expect(page.getByRole('link', { name: fixture.nodes[0].name, exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: fixture.nodes[2].name, exact: true })).toHaveCount(0);
  await page.getByLabel('Status', { exact: true }).selectOption('done');
  await expect(page.getByText('No results match these filters.', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Status', { exact: true })).toHaveValue('done');
  await expect(page.getByLabel('Weak only')).toBeChecked();
  await page.goBack();
  await expect(page.getByLabel('Status', { exact: true })).toHaveValue('not_started');
  await page.getByRole('link', { name: fixture.nodes[0].name, exact: true }).click();
  await page.getByRole('link', { name: '← Return', exact: true }).click();
  await expect(page).toHaveURL(/\/progress\?status=not_started&weak=true&sort=coverage_asc$/);
});

test('historical explanation shows recorded importance without a fabricated formula', async ({ page, request }) => {
  const fixture: Fixture = await (await request.get('/__test/fixture')).json();
  const id = fixture.nodes[0].id;
  const original: components['schemas']['ScoreExplanation'] = await (await request.get(`/api/v1/why/subtopic/${id}`)).json();
  const why: components['schemas']['ScoreExplanation'] = {
    ...original, explanation_status: 'historical_configuration_unavailable', error: 'Historical configuration unavailable.',
    configuration_source: null, importance_breakdown: { importance: .75, weights: null, exam: null, practice: null, weightage_prior: null },
    appearances: [], frequency: null, weightage_section: null,
  };
  await page.route(`**/api/v1/why/subtopic/${id}`, route => route.fulfill({ json: why }));
  await page.goto(`/papers/${fixture.paper_id}/${id}`);
  await expect(page.getByText('Importance: 75.0 / 100', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Why this importance?', exact: true }).click();
  await expect(page.getByText(/Historical configuration unavailable/)).toBeVisible();
  await expect(page.getByRole('table')).toHaveCount(0);
});

test('network failures remain errors on every live student page', async ({ page, request }) => {
  const fixture: Fixture = await (await request.get('/__test/fixture')).json();
  await page.route('**/api/v1/**', route => route.abort('failed'));
  for (const route of ['/', '/papers', '/plan', '/revision', '/progress', '/mock', `/papers/${fixture.paper_id}`]) {
    await page.goto(route);
    await expect(page.getByRole('alert').first()).toContainText('Unable to load');
    await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
    await expect(page.getByText('Demo Mode', { exact: true })).toHaveCount(0);
  }
});

test('route boundary leaves navigation and retry controls usable', async ({ page, request }) => {
  const dashboard: components['schemas']['Dashboard'] = await (await request.get('/api/v1/dashboard')).json();
  // Deliberately violate a response contract to exercise a render exception.
  await page.route('**/api/v1/dashboard', route => route.fulfill({ json: { ...dashboard, plan_preview: null } }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('This page could not render.');
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reload', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Study Plan', exact: true }).click();
  await expect(page.locator('ol li')).toHaveCount(2);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('production diagnostics expose the embedded build identity without private data', async ({ page }) => {
  await page.goto('/plan?notes=PRIVATE_NOTES&token=PRIVATE_TOKEN');
  await page.getByRole('button', { name: 'Diagnostics', exact: true }).click();
  await expect(page.locator('pre')).toContainText('browser-harness');
  const info = JSON.parse(await page.locator('pre').innerText());
  expect(info.frontend_revision).toMatch(/^[a-f0-9]{7,12}-[a-f0-9]{12}$/);
  expect(info.frontend_build).toBe(info.frontend_revision);
  expect(info.api_version).toBe('v1');
  expect(info.score_run.version).toBeTruthy();
  expect(info.route).toBe('/plan');
  expect(JSON.stringify(info)).not.toMatch(/PRIVATE_NOTES|PRIVATE_TOKEN/);
});
