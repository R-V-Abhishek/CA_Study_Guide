import { defineConfig, devices } from "@playwright/test";

const baseURL = `http://127.0.0.1:${process.env.CAF_BROWSER_PORT ?? '8765'}`;

export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: "list",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  // An explicitly managed sandbox server permits focused tests while iterating.
  webServer: process.env.CAF_BROWSER_EXTERNAL === '1' ? undefined : {
    command: "pnpm --dir web build && uv run scripts/browser_server.py",
    cwd: "..",
    url: `${baseURL}/__test/fixture`,
    reuseExistingServer: false,
    timeout: 120_000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
  },
});
