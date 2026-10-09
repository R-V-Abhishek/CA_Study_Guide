import { test as base, expect } from '@playwright/test';

/** API calls and page requests share the browser's cookie-backed session. */
export const test = base.extend({ request: async ({ context }, use) => { await use(context.request); } });
export { expect };
export const browserOrigin = `http://127.0.0.1:${process.env.CAF_BROWSER_PORT ?? '8765'}`;
export type { Page, APIRequestContext } from '@playwright/test';
