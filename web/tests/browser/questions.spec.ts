import { test, expect, type APIRequestContext } from './fixtures';

type ReaderFixture = { question_id: string; reader_part_id: string; source_id: number; paper_id: string; nodes: { id: string; name: string }[] };
async function fixture(request: APIRequestContext): Promise<ReaderFixture> { return (await request.get('/__test/fixture')).json(); }
test.beforeEach(async ({ request }) => { await request.post('/__test/reset'); await request.post('/__test/login'); });

test('published undated question reveals complete context and source, preserving filters', async ({ page, request }) => {
  const data = await fixture(request);
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/questions?q=Synthetic&answer_status=partial&source_family=practice');
  await expect(page.getByRole('link', { name: 'Synthetic reader question' })).toBeVisible();
  await page.getByRole('link', { name: 'Synthetic reader question' }).click();
  await expect(page.getByText('Synthetic shared case: a company considers two accounting requirements.')).toBeVisible();
  await expect(page.getByText('Synthetic first requirement.')).toBeVisible();
  await expect(page.getByText('Synthetic second requirement.')).toBeVisible();
  await expect(page.getByText('Undated collection', { exact: false })).toBeVisible();
  await expect(page.getByText('SYNTHETIC READER ANSWER SENTINEL')).toHaveCount(0);
  await page.getByRole('button', { name: 'Reveal answer' }).click();
  await expect(page.getByText('SYNTHETIC READER ANSWER SENTINEL')).toBeVisible();
  await expect(page.getByText('This answer is partial. Some parts have no reviewed answer.')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `test-results/phase6-reader-${test.info().project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: 'View page 1' }).click();
  await expect(page.getByRole('img', { name: 'Published question source page' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open published source' })).toHaveAttribute('href', `/api/v1/published-sources/${data.source_id}`);
  await page.getByRole('link', { name: '← Return', exact: true }).click();
  await expect(page.getByLabel('Search questions')).toHaveValue('Synthetic');
  await expect(page.getByLabel('Answer status')).toHaveValue('partial');
  await expect(page.getByLabel('Source family')).toHaveValue('practice');
  await page.reload();
  await expect(page.getByLabel('Answer status')).toHaveValue('partial');
  expect(errors).toEqual([]);
});

test('part highlight retains sibling parts and rejects external return URLs', async ({ page, request }) => {
  const data = await fixture(request);
  await page.goto(`/questions/${data.question_id}?part=${data.reader_part_id}&return=${encodeURIComponent('//example.test/steal')}`);
  await expect(page.locator('[data-selected=true]')).toContainText('Synthetic first requirement.');
  await expect(page.getByText('Synthetic second requirement.')).toBeVisible();
  await expect(page.getByText(/Selected part: 4 marks/)).toBeVisible();
  await expect(page.getByRole('link', { name: '← Return', exact: true })).toHaveAttribute('href', '/questions');
  await expect(page.getByText('Reading does not change your syllabus progress.')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `test-results/phase6-selected-part-${test.info().project.name}.png`, fullPage: true });
  const before = await (await request.get(`/api/v1/subtopics/${data.nodes[0].id}`)).json();
  expect(before.status).toBe('not_started');
});

test('question search filters and private notes enforce account scope', async ({ page, request }) => {
  const data = await fixture(request);
  const me = await (await request.get('/api/v1/me')).json();
  await request.put(`/api/v1/subtopics/${data.nodes[0].id}/notes`, { headers: { Origin: 'http://127.0.0.1:8765', 'X-CSRF-Token': me.csrf_token }, data: { notes: 'Synthetic private ownership sentinel' } });
  await page.goto('/questions?q=Synthetic&include_notes=true');
  await expect(page.getByText(`${data.nodes[0].id}: Synthetic private ownership sentinel`)).toBeVisible();
  await page.getByLabel('Answer status').selectOption('missing');
  await expect(page.getByText('No published questions match these filters.')).toBeVisible();
  await page.getByLabel('Answer status').selectOption('partial');
  await expect(page.getByRole('link', { name: 'Synthetic reader question' })).toBeVisible();
  await page.getByLabel('Search questions').fill('unfindablesynthetictoken');
  await expect(page.getByText('No matching notes.')).toBeVisible();
  await request.post('/__test/login?account_id=2');
  await page.reload();
  await page.getByLabel('Search questions').fill('Synthetic');
  await expect(page.getByText('No matching notes.')).toBeVisible();
  await expect(page.getByText('Synthetic private ownership sentinel', { exact: false })).toHaveCount(0);
});

test('explicit question demo works without API traffic', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/v1/')) requests.push(request.url()); });
  await page.goto('/questions?demo=true');
  await page.getByRole('link', { name: 'Demo complete question' }).click();
  await expect(page.getByText('A company enters into a lease. Both parts use this shared case.')).toBeVisible();
  await page.getByRole('button', { name: 'Reveal answer' }).click();
  await expect(page.getByText(/This is a synthetic demo answer/)).toBeVisible();
  expect(requests).toEqual([]);
});
