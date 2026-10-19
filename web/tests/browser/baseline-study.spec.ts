import { test, expect } from './fixtures';
import type { PublishedQuestion } from '../../packages/api-client/src/questions';

test.beforeEach(async ({ request }) => {
  await request.post('/__test/reset');
});

test('baseline provenance preserves unresolved labels and pending P5 applicability without student attestations', async ({ page, request }) => {
  await request.post('/__test/login');
  const fixture = await (await request.get('/__test/fixture')).json();
  const original: PublishedQuestion = await (await request.get(`/api/v1/questions/${fixture.question_id}`)).json();
  const baseline: PublishedQuestion = {
    ...original,
    verification_count: 0,
    content: { ...original.content, paper_id: 's2023.P5' },
    extraction_quality: {
      ...original.extraction_quality,
      baseline: { release_id: 'baseline-2026-10-16', manifest_hash: 'a'.repeat(64), scope: 'study_and_review', applicability_status: 'source_evidence_only_target_review_required' },
      unresolved_parts: [original.content.parts[0].id, original.content.parts[1].id],
    },
  };
  await page.route(`**/api/v1/questions/${fixture.question_id}`, route => route.fulfill({ json: baseline }));
  await page.goto(`/questions/${fixture.question_id}`);
  await page.getByRole('tab', { name: 'Extracted text', exact: true }).click();
  const provenance = page.getByRole('region', { name: 'Baseline provenance' });
  await expect(provenance).not.toContainText('Adopted baseline baseline-2026-10-16');
  await expect(provenance).toContainText('Topic labels remain unresolved for 2 parts.');
  await expect(provenance).toContainText('May 2027 applicability review pending.');
  await expect(provenance).toContainText('P5 includes older-edition material');
  await expect(page.getByText('Topic labels verified by 0 students').first()).toBeVisible();
  await page.screenshot({ path: `test-results/baseline-provenance-${test.info().project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: 'Topics and outline', exact: true }).click();
  await page.getByRole('dialog', { name: 'Parts and evidence' }).getByRole('button', { name: 'Content details', exact: true }).click();
  const details = page.getByRole('dialog', { name: 'Content details' });
  await details.getByText('Technical details', { exact: true }).click();
  await expect(details).toContainText(`Baseline manifest SHA-256 ${'a'.repeat(64)}`);
});

test('long complete, partial and missing answers remain distinguishable and sources retain the full case', async ({ page, request }) => {
  await request.post('/__test/login');
  await page.goto('/questions/synthetic.reader.complete');
  await page.getByRole('tab', { name: 'Extracted text', exact: true }).click();
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
  await page.getByRole('tab', { name: 'Extracted text', exact: true }).click();
  await page.getByRole('button', { name: 'Reveal answer' }).click();
  await expect(page.getByText('This answer is partial. Some parts have no reviewed answer.')).toBeVisible();
  await page.goto('/questions/synthetic.reader.missing');
  await page.getByRole('tab', { name: 'Extracted text', exact: true }).click();
  await expect(page.getByText('No reviewed answer is available for this question.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reveal answer' })).toHaveCount(0);
});

test('ordinary workspaces have no preview setup or synthetic account controls', async ({ page, request }) => {
  await request.post('/__test/login');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Acceptance environment' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Study as Student A' })).toHaveCount(0);
  await request.post('/__test/login?account_id=3');
  await page.goto('/curator/classifications');
  await expect(page.getByRole('heading', { name: 'Review questions', exact: true })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Real data preview' })).toHaveCount(0);
});
