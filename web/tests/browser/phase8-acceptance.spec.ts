import { test, expect } from './fixtures';

test.beforeEach(async ({ request }) => {
  const response = await request.get('/__acceptance/feedback');
  test.skip(!response.headers()['content-type']?.startsWith('application/json'), 'Requires the explicit local acceptance harness');
});

test('acceptance identities use private sessions and keep the synthetic label across both workspaces', async ({ page, request }) => {
  await page.goto('/__acceptance');
  await page.getByRole('button', { name: 'Study as Student A' }).click();
  await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Acceptance environment' })).toContainText('SYNTHETIC DATA');
  const banner = await page.getByRole('complementary', { name: 'Acceptance environment' }).boundingBox();
  const brand = await page.getByRole('link', { name: 'CA Final Prep', exact: true }).boundingBox();
  expect(brand!.y).toBeGreaterThanOrEqual(banner!.y + banner!.height);
  const student = await (await request.get('/api/v1/me')).json();
  expect(student.account.id).toBe(1);
  expect(student.capabilities).not.toContain('admin');
  const cookies = await page.context().cookies();
  expect(cookies.some(cookie => cookie.name === 'caf_acceptance_session')).toBe(true);
  expect(cookies.some(cookie => cookie.name === 'caf_session')).toBe(false);
  expect((await request.get('/api/v1/admin/accounts')).status()).toBe(403);
  await page.goto('/__acceptance');
  await page.getByRole('button', { name: 'Review as Administrator' }).click();
  await expect(page.getByRole('heading', { name: 'Review questions', exact: true })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Acceptance environment' })).toBeVisible();
  const admin = await (await request.get('/api/v1/me')).json();
  expect(admin.account.id).toBe(3);
  expect(admin.capabilities).toContain('admin');
});

test('long complete, partial and missing answers remain distinguishable and sources retain the full case', async ({ page, request }) => {
  await request.post('/__test/login');
  await page.goto('/questions/synthetic.reader.complete');
  await expect(page.getByText(/Case paragraph 16:/)).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
  await page.getByRole('button', { name: 'Reveal answer' }).click();
  await expect(page.getByText('Synthetic complete answer for part (b).')).toBeVisible();
  await page.getByRole('button', { name: 'View source', exact: true }).last().click();
  const source = page.getByRole('dialog', { name: 'Source and pages' });
  await expect(source.getByRole('img')).toBeVisible();
  await expect(source.getByLabel('Page', { exact: true }).locator('option')).not.toHaveCount(1);
  const sourceUrl = await source.getByRole('link', { name: 'Open PDF' }).getAttribute('href');
  const pdf = await request.get(sourceUrl!);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()['content-type']).toContain('application/pdf');
  await page.goto('/questions/synthetic.reader');
  await page.getByRole('button', { name: 'Reveal answer' }).click();
  await expect(page.getByText('This answer is partial. Some parts have no reviewed answer.')).toBeVisible();
  await page.goto('/questions/synthetic.reader.missing');
  await expect(page.getByText('No reviewed answer is available for this question.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reveal answer' })).toHaveCount(0);
});

test('human feedback requires the current account and CSRF and persists after navigation', async ({ page, request }) => {
  const unsigned = await request.post('/__acceptance/feedback', { data: { area: 'appearance', status: 'Approved' } });
  expect(unsigned.status()).toBe(401);
  await page.goto('/__acceptance');
  await page.getByRole('button', { name: 'Study as Student B' }).click();
  await page.goto('/__acceptance');
  const form = page.locator('[data-area="appearance"]');
  await form.getByLabel('Judgment').selectOption('Changes requested');
  await form.getByLabel('Screen').fill('Synthetic acceptance test screen');
  await form.getByLabel('Observation').fill('AUTOMATED TEST ONLY: does not establish human approval.');
  await form.getByRole('button', { name: 'Save feedback' }).click();
  await expect(form.locator('output')).toHaveText('Saved.');
  await page.reload();
  await expect(form.getByLabel('Observation')).toHaveValue('AUTOMATED TEST ONLY: does not establish human approval.');
  const forged = await request.post('/__acceptance/feedback', { data: { area: 'appearance', status: 'Approved' } });
  expect(forged.status()).toBe(403);
  const evidence = await (await request.get('/__acceptance/feedback')).json();
  const observation = evidence.observations.find((row: { area: string }) => row.area === 'appearance');
  expect(observation.fixture_account_id).toBe(2);
  expect(observation.status).toBe('Changes requested');
});
