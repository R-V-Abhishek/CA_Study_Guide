import { test as base, expect } from '@playwright/test';

/** API calls and page requests share the browser's cookie-backed session. */
export const test = base.extend({ request: async ({ context }, use) => { await use(context.request); } });
export { expect };
export const browserOrigin = () => test.info().project.use.baseURL!;
export type { Page, APIRequestContext } from '@playwright/test';
