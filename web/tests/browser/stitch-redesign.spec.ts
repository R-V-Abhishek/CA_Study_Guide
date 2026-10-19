import { test, expect } from './fixtures';
import { classificationItem } from './classification-fixture';

test.beforeEach(async ({ request }) => { await request.post('/__test/reset'); });

for (const colorScheme of ['light', 'dark'] as const) {
  test(`dark default and invalid preference under ${colorScheme} OS`, async ({ page, request }) => {
    await request.post('/__test/login');
    await page.emulateMedia({ colorScheme });
    for (const path of ['/', '/curator/classifications']) {
      await page.goto(path);
      await expect(page.locator('html')).toHaveClass(/dark/);
      expect(await page.evaluate(() => localStorage.getItem('caf_theme'))).toBeNull();
      await page.evaluate(() => localStorage.setItem('caf_theme', 'obsolete'));
      await page.reload();
      await expect(page.locator('html')).toHaveClass(/dark/);
      await page.evaluate(() => localStorage.removeItem('caf_theme'));
    }
  });
}

test('explicit appearance synchronises open workspaces, reload and OS changes', async ({ page, context, request }) => {
  await request.post('/__test/login');
  await page.goto('/profile');
  const other = await context.newPage();
  await other.emulateMedia({ colorScheme: 'light' });
  await other.goto('/curator/classifications');
  const appearance = page.locator('main').getByLabel('Appearance');
  for (const value of ['light', 'dark', 'system']) {
    await appearance.selectOption(value);
    await expect.poll(() => other.evaluate(() => localStorage.getItem('caf_theme'))).toBe(value);
    await expect(other.locator('html')).toHaveClass(value === 'dark' ? /dark/ : /^$/);
    await other.reload();
    await expect(other.locator('html')).toHaveClass(value === 'dark' ? /dark/ : /^$/);
  }
  await other.emulateMedia({ colorScheme: 'dark' });
  await expect(other.locator('html')).toHaveClass(/dark/);
  await other.close();
});

// Run explicitly for acceptance. Each route has viewport and full-page evidence.
// The files are captures, not evidence of human visual approval.
for (const variant of [
  { width: 1440, height: 900, theme: 'dark' },
  { width: 390, height: 844, theme: 'dark' },
  { width: 1440, height: 900, theme: 'light' },
  { width: 390, height: 844, theme: 'light' },
] as const) {
  test(`@visual all routes ${variant.width} ${variant.theme}`, async ({ page, request }, info) => {
    test.setTimeout(240_000);
    await request.post('/__test/reset');
    await request.post('/__test/login?account_id=3');
    const fixture = await (await request.get('/__test/fixture')).json();
    await page.setViewportSize(variant);
    await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
    if (variant.theme === 'light') await page.addInitScript(() => localStorage.setItem('caf_theme', 'light'));
    await page.route('**/api/v1/curate/classifications?*', route => route.fulfill({ json: [classificationItem] }));
    const routes = [
      ['today', '/'], ['papers', '/papers'], ['paper', `/papers/${fixture.paper_id}`],
      ['topic-deep-link', `/papers/${fixture.paper_id}/${fixture.nodes[0].id}`],
      ['syllabus', '/syllabus'], ['topic', `/syllabus?paper=${fixture.paper_id}&node=${fixture.nodes[0].id}`],
      ['notes', `/syllabus?paper=${fixture.paper_id}&node=${fixture.nodes[0].id}&tab=notes`],
      ['importance', `/syllabus?paper=${fixture.paper_id}&node=${fixture.nodes[0].id}&tab=importance`],
      ['draft', '/syllabus?preview=draft'], ['textbooks-alias', '/textbooks'],
      ['questions', '/questions'], ['filtered-empty', '/questions?q=not-a-fixture-match'],
      ['reader', `/questions/${fixture.question_id}`], ['plan', '/plan?adjust=true'],
      ['revision', '/revision'], ['progress', '/progress'], ['coverage', '/progress?tab=coverage'], ['progress-importance', '/progress?tab=importance'],
      ['mock', '/mock'], ['profile', '/profile'], ['not-found', '/unavailable'],
      ...['classifications', 'extraction', 'textbooks', 'syllabus', 'taxonomy-release', 'readiness', 'documents', 'catalog', 'catalogue', 'bulk', 'accounts', 'system', 'queue', 'taxonomy'].map(name => [`review-${name}`, `/curator/${name}`]),
    ];
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const [name, url] of routes) {
      await page.goto(url);
      await expect(page.locator('main h1').first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('[aria-busy=true]')).toHaveCount(0);
      await expect(page.locator('main h1').first()).toBeVisible();
      await expect(page.locator('html')).toHaveClass(variant.theme === 'dark' ? /dark/ : /^$/);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), url).toBe(true);
      const stem = `../docs/stitch-review/${info.project.name}-${name}-${variant.width}-${variant.theme}`;
      await page.screenshot({ path: `${stem}-viewport.png` });
      await page.screenshot({ path: `${stem}-full.png`, fullPage: true });
      if (name === 'reader') {
        await page.getByRole('tab', { name: 'Extracted text', exact: true }).click();
        await page.getByRole('button', { name: 'Reveal answer' }).click();
        await expect(page.getByText('SYNTHETIC READER ANSWER SENTINEL')).toBeVisible();
        await page.screenshot({ path: `${stem}-answer-full.png`, fullPage: true });
        await page.getByRole('button', { name: 'View source', exact: true }).last().click();
        await expect(page.getByRole('dialog').getByRole('img')).toBeVisible();
        await page.screenshot({ path: `${stem}-source-viewport.png` });
        await page.keyboard.press('Escape');
      }
    }
    expect(errors).toEqual([]);
  });
}

for (const size of [{ width: 1280, height: 800 }, { width: 1024, height: 768 }, { width: 768, height: 1024 }]) {
  test(`@visual major layouts ${size.width}`, async ({ page, request }, info) => {
    await request.post('/__test/login?account_id=3');
    const fixture = await (await request.get('/__test/fixture')).json();
    await page.setViewportSize(size);
    await page.route('**/api/v1/curate/classifications?*', route => route.fulfill({ json: [classificationItem] }));
    for (const [name, url] of [['today', '/'], ['questions', '/questions'], ['syllabus', `/syllabus?paper=${fixture.paper_id}&node=${fixture.nodes[0].id}`], ['reader', `/questions/${fixture.question_id}`], ['review', '/curator/classifications']]) {
      await page.goto(url);
      await expect(page.locator('main h1').first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('[aria-busy=true]')).toHaveCount(0);
      await expect(page.locator('main h1').first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      const stem = `../docs/stitch-review/${info.project.name}-${name}-${size.width}-dark`;
      await page.screenshot({ path: `${stem}-viewport.png` });
      await page.screenshot({ path: `${stem}-full.png`, fullPage: true });
    }
  });
}

test('account access changes require confirmation and cancellation sends no mutation', async ({ page, request }) => {
  await request.post('/__test/login?account_id=3');
  let updates = 0;
  await page.route('**/api/v1/admin/accounts/*', route => {
    if (route.request().method() !== 'PATCH') return route.continue();
    updates++;
    return route.fulfill({ json: { id: 1 } });
  });
  await page.goto('/curator/accounts');
  const role = page.getByRole('combobox', { name: /^Role/ }).first();
  await expect(role).toBeVisible();
  const next = await role.inputValue() === 'student' ? 'administrator' : 'student';
  await role.selectOption(next);
  const dialog = page.getByRole('dialog', { name: 'Confirm account access change' });
  await expect(dialog).toBeVisible();
  expect(updates).toBe(0);
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).not.toBeVisible();
  expect(updates).toBe(0);
  await role.selectOption(next);
  await dialog.getByRole('button', { name: 'Confirm change' }).click();
  await expect(dialog).not.toBeVisible();
  expect(updates).toBe(1);
});
