import { test, expect } from './fixtures';

test.beforeEach(async ({ request }) => { await request.post('/__test/reset'); await request.post('/__test/login'); });

test('original pages are default, text is optional and returning reuses the private image cache', async ({ page, request }) => {
  const fixture = await (await request.get('/__test/fixture')).json();
  let images = 0;
  page.on('request', request => { if (/\/questions\/[^/]+\/pages\/question\//.test(request.url())) images++; });
  await page.goto(`/questions/${fixture.question_id}`);
  await expect(page.getByRole('tab', { name: 'Original pages', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('img', { name: 'Question, source page 1', exact: true })).toBeVisible();
  const initial = images;
  expect(initial).toBeGreaterThan(0);
  await page.getByRole('tab', { name: 'Extracted text', exact: true }).click();
  await expect(page.getByText('Synthetic first requirement.', { exact: true })).toBeVisible();
  await expect(page.getByText('Synthetic second requirement.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reveal answer', exact: true }).click();
  await expect(page.getByText('SYNTHETIC READER ANSWER SENTINEL')).toBeVisible();
  await page.getByRole('tab', { name: 'Original pages', exact: true }).click();
  await expect(page.getByRole('img', { name: 'Question, source page 1', exact: true })).toBeVisible();
  expect(images).toBe(initial);
  await page.getByLabel('Focus on relevant question area', { exact: true }).first().check();
  await expect.poll(() => images).toBeGreaterThan(initial);
});

test('later pages wait until near the viewport', async ({ page, request }) => {
  const fixture = await (await request.get('/__test/fixture')).json();
  const original = await (await request.get(`/api/v1/questions/${fixture.question_id}`)).json();
  const first = original.question_pages[0];
  await page.route(`**/api/v1/questions/${fixture.question_id}`, route => route.fulfill({ json: {
    ...original, question_pages: Array.from({ length: 12 }, (_, index) => ({ ...first, page: index + 1,
      url: first.url.replace(/\/\d+$/, `/${index + 1}`) })),
  } }));
  const loaded: string[] = [];
  await page.route('**/questions/*/pages/question/**', route => {
    loaded.push(route.request().url());
    return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100"><rect width="800" height="1100" fill="white"/></svg>' });
  });
  await page.goto(`/questions/${fixture.question_id}`);
  await expect(page.getByRole('img').first()).toBeVisible();
  expect(loaded.some(url => /\/12\?/.test(url))).toBe(false);
  await page.getByText('Question · Source page 12', { exact: true }).scrollIntoViewIfNeeded();
  await expect.poll(() => loaded.some(url => /\/12\?/.test(url))).toBe(true);
});

test('Hindi opt-in is saved in Profile', async ({ page }) => {
  await page.goto('/profile');
  const flag = page.getByLabel('Include Hindi questions', { exact: true });
  await expect(flag).not.toBeChecked();
  await flag.check();
  await page.getByRole('button', { name: 'Save settings', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Settings saved.' })).toBeVisible();
  await page.reload();
  await expect(flag).toBeChecked();
});
