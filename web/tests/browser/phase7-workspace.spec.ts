import { test, expect, type Page } from './fixtures';
import { classificationItem } from './classification-fixture';

async function contained(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}
async function capture(page: Page, name: string, width: number, theme: string) {
  if (test.info().project.name === 'chromium' && (width === 390 || width === 1440)) {
    await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: `../docs/phase7-screenshots/${name}-${width}-${theme}.png`, fullPage: true });
  }
}
test.beforeEach(async ({ request }) => { await request.post('/__test/reset'); await request.post('/__test/login'); });

for (const width of [390, 768, 1280, 1440]) for (const theme of ['light', 'dark'] as const) {
  test(`study and review workspace ${width}px ${theme}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript(value => localStorage.setItem('caf_theme', value), theme);
    const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
    const fixture = await (await request.get('/__test/fixture')).json();
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Continue studying', exact: true })).toBeVisible();
    await expect(page.locator('html')).toHaveClass(theme === 'dark' ? /dark/ : /^$/);
    expect(await page.evaluate(() => localStorage.getItem('caf_theme'))).toBe(theme);
    await contained(page);
    await capture(page, 'today', width, theme);
    if (width < 768) {
      const more = page.getByRole('button', { name: 'More', exact: true });
      await more.click();
      const sheet = page.getByRole('dialog', { name: 'More destinations' });
      await expect(sheet.getByRole('link', { name: 'Mock results' })).toBeVisible();
      await page.keyboard.press('Escape'); await expect(more).toBeFocused();
      await expect(sheet).not.toBeVisible();
    } else if (width < 1024) {
      const menu = page.getByRole('button', { name: 'Menu', exact: true });
      await menu.click(); await expect(page.getByRole('dialog', { name: 'Study navigation' })).toBeVisible();
      await page.keyboard.press('Escape'); await expect(menu).toBeFocused();
    } else {
      await expect(page.getByRole('navigation', { name: 'Study navigation', exact: true })).toBeVisible();
    }
    await page.goto(`/syllabus?paper=${fixture.paper_id}&search=${encodeURIComponent(fixture.nodes[0].name)}`);
    await expect(page.getByRole('tree', { name: 'Syllabus hierarchy' })).toBeVisible();
    const first = page.getByRole('treeitem').first();
    await first.focus(); await page.keyboard.press('End');
    await expect(page.getByRole('treeitem').last()).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('tab', { name: 'My notes' })).toBeVisible();
    await expect(page).toHaveURL(/node=/);
    await contained(page);
    await capture(page, 'syllabus', width, theme);
    await page.goto(`/questions/${fixture.question_id}?part=${fixture.reader_part_id}&return=${encodeURIComponent('/questions?q=Synthetic&page=1')}`);
    await page.getByRole('tab', { name: 'Extracted text', exact: true }).click();
    await expect(page.locator('[data-selected=true]')).toContainText('Synthetic first requirement.');
    await expect(page.getByText('Synthetic second requirement.')).toBeVisible();
    await page.getByRole('button', { name: 'Reveal answer' }).click();
    await expect(page.getByText('SYNTHETIC READER ANSWER SENTINEL')).toBeVisible();
    await capture(page, 'reader', width, theme); await contained(page);
    const source = page.getByRole('button', { name: 'View source', exact: true }).last();
    await source.click();
    const dialog = page.getByRole('dialog', { name: 'Source and pages' });
    await expect(dialog.getByRole('img')).toBeVisible();
    await expect(dialog.getByRole('link', { name: 'Open PDF' })).toBeVisible();
    await page.keyboard.press('Escape'); await expect(source).toBeFocused();
    await page.getByRole('link', { name: '← Back to questions' }).click();
    await expect(page.getByLabel('Search questions', { exact: true })).toHaveValue('Synthetic');
    await request.post('/__test/login?account_id=3');
    await page.route('**/api/v1/curate/classifications?*', route => route.fulfill({ json: [classificationItem] }));
    await page.goto('/curator/classifications');
    await expect(page.getByRole('heading', { name: 'Review questions', exact: true })).toBeVisible();
    if (width < 1280) {
      await page.getByRole('tab', { name: 'Labels', exact: true }).click();
      await page.getByLabel('Review evidence or correction reason').fill('Evidence retained across mobile panes');
      await page.getByRole('tab', { name: 'Question', exact: true }).click();
      await expect(page.getByText('Company case shared by both parts.')).toBeVisible();
      await page.getByRole('tab', { name: 'Answer', exact: true }).click();
      await expect(page.getByText('Revenue is 100.')).toBeVisible();
      await page.getByRole('tab', { name: 'Labels', exact: true }).click();
      await expect(page.getByLabel('Review evidence or correction reason')).toHaveValue('Evidence retained across mobile panes');
    } else {
      await expect(page.getByText('Company case shared by both parts.')).toBeVisible();
    }
    await capture(page, 'classification', width, theme); await contained(page);
    expect(errors).toEqual([]);
  });
}

test('explicit theme persists across workspaces and System follows OS', async ({ page, request }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/'); await expect(page.locator('html')).toHaveClass(/dark/);
  await page.locator('.workspace-sidebar .account-menu > summary').click();
  const appearance = page.locator('.workspace-sidebar').getByLabel('Appearance');
  await appearance.selectOption('light'); await expect(page.locator('html')).not.toHaveClass(/dark/);
  await page.emulateMedia({ colorScheme: 'dark' }); await page.reload();
  await expect(page.locator('html')).not.toHaveClass(/dark/);
  await request.post('/__test/login?account_id=3'); await page.goto('/curator/classifications');
  await expect(page.locator('html')).not.toHaveClass(/dark/);
  await page.locator('.curator-sidebar .account-menu > summary').click();
  await page.locator('.curator-sidebar').getByLabel('Appearance').selectOption('system');
  await expect(page.locator('html')).toHaveClass(/dark/);
  expect(await page.evaluate(() => localStorage.getItem('caf_theme'))).toBe('system');
});

test('200% zoom keeps reader controls reachable and scrolling inside content canvases', async ({ page, request }) => {
  const fixture = await (await request.get('/__test/fixture')).json();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`/questions/${fixture.question_id}`);
  await page.getByRole('tab', { name: 'Extracted text', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Reveal answer' })).toBeVisible();
  await page.evaluate(() => { document.documentElement.style.zoom = '2'; });
  await page.getByRole('button', { name: 'Reveal answer' }).click();
  await expect(page.getByText('SYNTHETIC READER ANSWER SENTINEL')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
  await page.getByRole('button', { name: 'View source', exact: true }).last().click();
  await expect(page.getByRole('dialog', { name: 'Source and pages' }).getByRole('button', { name: 'Close' })).toBeVisible();
  await page.keyboard.press('Escape');
});
