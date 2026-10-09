import { test, expect, browserOrigin } from './fixtures';

test.beforeEach(async ({ request }) => { expect((await request.post('/__test/reset')).ok()).toBe(true); });

test('provider registration grants no access without a matching invitation', async ({ page, request }) => {
  await page.goto('/auth/login');
  await page.getByRole('link', { name: 'Invited new student' }).click();
  await expect(page.getByRole('heading', { name: 'Invitation required' })).toBeVisible();
  expect((await request.get('/api/v1/me')).status()).toBe(401);
  await request.post('/__test/login?account_id=3');
  const me = await (await request.get('/api/v1/me')).json();
  const invitation = await (await request.post('/api/v1/admin/invitations', { headers: { Origin: browserOrigin(), 'X-CSRF-Token': me.csrf_token }, data: { email: 'wrong.email@example.test' } })).json();
  await page.goto(invitation.invitation_url);
  await page.getByRole('link', { name: 'Invited new student' }).click();
  await expect(page.getByRole('heading', { name: 'Invitation email mismatch' })).toBeVisible();
  const invites = await (await request.get('/api/v1/admin/invitations')).json();
  expect(invites[0].consumed_at).toBeNull();
});

test('hosted OIDC invitation creates a private profile with honest unavailable scores', async ({ page, request }) => {
  await request.post('/__test/login?account_id=3');
  const me = await (await request.get('/api/v1/me')).json();
  const invite = await (await request.post('/api/v1/admin/invitations', { headers: { Origin: browserOrigin(), 'X-CSRF-Token': me.csrf_token }, data: { email: 'new.student@example.test' } })).json();
  await page.goto(invite.invitation_url);
  await expect(page.getByRole('heading', { name: 'Browser harness identity provider' })).toBeVisible();
  await page.getByRole('link', { name: 'Invited new student' }).click();
  await page.goto('/profile');
  await expect(page.getByLabel('Target attempt')).toHaveValue('2027-05');
  await expect(page.getByLabel('Weekly hours')).toHaveValue('20');
  await expect(page.getByLabel('Revision intervals in days')).toHaveValue('3, 7, 21, 60');
  await page.getByLabel('Display name').fill('New invited profile');
  await page.getByRole('button', { name: 'Save settings' }).click();
  await expect(page.getByRole('status')).toHaveText('Settings saved.');
  await page.goto('/plan');
  await expect(page.getByText(/^Syllabus-based ·/)).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('link', { name: 'Sign in with Auth0' })).toBeVisible();
  await expect.poll(async () => (await request.get('/api/v1/me')).status()).toBe(401);
});

test('two independent sessions keep notes, settings and exports private', async ({ browser, page, request }) => {
  await request.post('/__test/login');
  const fixture = await (await request.get('/__test/fixture')).json();
  const other = await browser.newContext({ baseURL: browserOrigin() });
  await other.request.post('/__test/login?account_id=2');
  const second = await other.newPage();
  const destination = `/papers/${fixture.paper_id}/${fixture.nodes[0].id}?tab=notes`;
  await page.goto(destination); await second.goto(destination);
  await page.getByRole('textbox', { name: 'Notes', exact: true }).fill('PRIVATE STUDENT A NOTES');
  await page.getByRole('button', { name: 'Save notes' }).click();
  await expect(page.getByRole('status').filter({ hasText: /^Saved$/ })).toBeVisible();
  await expect(second.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('');
  await second.getByRole('textbox', { name: 'Notes', exact: true }).fill('PRIVATE STUDENT B NOTES');
  await second.getByRole('button', { name: 'Save notes' }).click();
  await expect(second.getByRole('status').filter({ hasText: /^Saved$/ })).toBeVisible();
  const firstExport = JSON.stringify(await (await request.get('/api/v1/me/export')).json());
  const secondExport = JSON.stringify(await (await other.request.get('/api/v1/me/export')).json());
  expect(firstExport).toContain('PRIVATE STUDENT A NOTES'); expect(firstExport).not.toContain('PRIVATE STUDENT B NOTES');
  expect(secondExport).toContain('PRIVATE STUDENT B NOTES'); expect(secondExport).not.toContain('PRIVATE STUDENT A NOTES');
  await page.goto('/curator/system');
  await expect(page.getByRole('alert')).toContainText('Administrator access required.');
  await expect(page.getByRole('link', { name: 'Bulk Accept' })).toHaveCount(0);
  await other.close();
});

test('logout clears both application tabs and cancels pending notes', async ({ page, request, context }) => {
  await request.post('/__test/login');
  const fixture = await (await request.get('/__test/fixture')).json();
  await page.goto(`/papers/${fixture.paper_id}/${fixture.nodes[0].id}?tab=notes`);
  const curator = await context.newPage(); await curator.goto('/curator/queue');
  await curator.getByRole('button', { name: 'Menu', exact: true }).click();
  await expect(curator.getByRole('button', { name: 'Sign out' })).toBeVisible();
  let saves = 0; page.on('request', request => { if (request.method() === 'PUT' && request.url().endsWith('/notes')) saves++; });
  await page.getByRole('textbox', { name: 'Notes', exact: true }).fill('UNSAVED PRIVATE DRAFT');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('link', { name: 'Sign in with Auth0' })).toBeVisible();
  await expect(curator.getByRole('link', { name: 'Sign in with Auth0' })).toBeVisible();
  await page.waitForTimeout(1200); expect(saves).toBe(0);
  await request.post('/__test/login?account_id=2');
  await page.reload();
  await expect(page.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('');
});

test('account changes reject late private responses and discard account drafts', async ({ page, request }) => {
  await request.post('/__test/login');
  const fixture = await (await request.get('/__test/fixture')).json();
  const path = `/api/v1/subtopics/${fixture.nodes[0].id}`;
  const original = await (await request.get(path)).json();
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  let started!: () => void; const intercepted = new Promise<void>(resolve => { started = resolve; });
  let first = true;
  await page.route(`**${path}`, async route => {
    if (!first) { await route.continue(); return; }
    first = false;
    expect(route.request().headers()['x-expected-account-id']).toBe('1');
    started(); await gate; await route.fulfill({ json: { ...original, notes: 'LATE PRIVATE A RESPONSE' } }).catch(() => undefined);
  });
  await page.goto(`/papers/${fixture.paper_id}/${fixture.nodes[0].id}?tab=notes`);
  await intercepted;
  await request.post('/__test/login?account_id=2');
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('link', { name: /Student B · Profile/ })).toBeVisible();
  release();
  await expect(page.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('');
  await expect(page.getByText('LATE PRIVATE A RESPONSE')).toHaveCount(0);
});

test('storage fallback broadcasts an account change to the other application', async ({ context, page, request }) => {
  await context.addInitScript(() => { Object.defineProperty(window, 'BroadcastChannel', { value: undefined }); });
  await request.post('/__test/login');
  const fixture = await (await request.get('/__test/fixture')).json();
  await page.goto(`/papers/${fixture.paper_id}/${fixture.nodes[0].id}?tab=notes`);
  await expect(page.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('');
  const curator = await context.newPage(); await curator.goto('/curator/queue');
  await curator.getByRole('button', { name: 'Menu', exact: true }).click();
  await expect(curator.getByRole('link', { name: /Browser fixture student · Profile/ })).toBeVisible();
  await request.post('/__test/login?account_id=2');
  await curator.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(curator.getByRole('link', { name: /Browser fixture student · Profile/ })).not.toBeVisible();
  await curator.getByRole('button', { name: 'Menu', exact: true }).click();
  await expect(curator.getByRole('link', { name: /Student B · Profile/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /Student B · Profile/ })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('');
});

test('an unseen cookie switch rejects a stale account read before showing private data', async ({ page, request }) => {
  await request.post('/__test/login');
  await page.goto('/plan');
  await expect(page.locator('ol li')).toHaveCount(2);
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  let started!: () => void; const intercepted = new Promise<void>(resolve => { started = resolve; });
  await page.route('**/api/v1/plan*', async route => {
    const response = await route.fetch();
    started(); await gate;
    await route.fulfill({ response }).catch(() => undefined);
  });
  await page.getByText('Adjust plan', { exact: true }).click();
  await page.getByRole('button', { name: 'Refresh plan' }).click(); await intercepted;
  await request.post('/__test/login?account_id=2');
  const me = await (await request.get('/api/v1/me')).json();
  const settings = await (await request.get('/api/v1/me/settings')).json();
  const { groups: _groups, available_papers: _papers, available_attempts: _attempts, ...body } = settings;
  expect((await request.put('/api/v1/me/settings', { headers: { Origin: browserOrigin(), 'X-CSRF-Token': me.csrf_token }, data: { ...body, target_attempt_id: '2027-05' } })).ok()).toBe(true);
  const mismatch = page.waitForResponse(response => response.url().endsWith('/api/v1/dashboard') && response.status() === 409);
  await page.getByRole('link', { name: 'Today', exact: true }).click(); await mismatch;
  await expect(page.getByRole('link', { name: /Student B · Profile/ })).toBeVisible();
  await expect(page.getByText(/Target attempt May 2027/)).toBeVisible();
  release(); await page.unroute('**/api/v1/plan*');
  await page.getByRole('link', { name: 'Plan', exact: true }).click();
  await expect(page.getByText(/^Syllabus-based ·/)).toBeVisible();
  await page.locator('main summary').filter({ hasText: 'Technical details' }).click();
  await expect(page.getByText(/Target 2027-05/)).toBeVisible();
  await expect(page.getByText(/^Historically ranked ·/)).toHaveCount(0);
});

test('a matching profile update preserves unsaved notes in another tab', async ({ page, context, request }) => {
  await request.post('/__test/login');
  const fixture = await (await request.get('/__test/fixture')).json();
  await page.route('**/notes', route => route.fulfill({ status: 503, json: { detail: 'Save temporarily unavailable' } }));
  await page.goto(`/papers/${fixture.paper_id}/${fixture.nodes[0].id}?tab=notes`);
  const profile = await context.newPage(); await profile.goto('/profile');
  await page.getByRole('textbox', { name: 'Notes', exact: true }).fill('KEEP THIS UNSAVED OWN ACCOUNT DRAFT');
  await expect(page.getByRole('status').filter({ hasText: 'Save failed' })).toBeVisible();
  await profile.getByLabel('Display name').fill('Updated own profile');
  await profile.getByRole('button', { name: 'Save settings' }).click();
  await expect(profile.getByRole('status')).toHaveText('Settings saved.');
  await expect(page.getByRole('link', { name: /Updated own profile · Profile/ })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('KEEP THIS UNSAVED OWN ACCOUNT DRAFT');
  expect((await (await request.get(`/api/v1/subtopics/${fixture.nodes[0].id}`)).json()).notes).toBeNull();
  await page.route('**/api/v1/me', route => route.abort('failed'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('heading', { name: 'Sign-in unavailable' })).toBeVisible();
  await page.unroute('**/api/v1/me');
  await page.getByRole('button', { name: 'Check again' }).click();
  await expect(page.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('KEEP THIS UNSAVED OWN ACCOUNT DRAFT');
});
