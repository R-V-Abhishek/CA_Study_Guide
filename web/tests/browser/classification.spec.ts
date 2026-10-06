import { test, expect, type Page } from "./fixtures";
import type { ClassificationQueueItem } from "../../packages/api-client/src/classification";
import { classificationItem as item, classificationMapping as mapping } from "./classification-fixture";

async function queue(page: Page, value: ClassificationQueueItem = item) {
  await page.route("**/api/v1/curate/classifications?**", route => {
    const blind = new URL(route.request().url()).searchParams.get("blind") === "true";
    return route.fulfill({ json: [{ ...value, ...(blind ? { blind: true, mappings: [{ part_id: mapping.part_id, outcome: "needs_review" }], provenance: {}, published_mappings: [] } : {}) }] });
  });
}
test.beforeEach(async ({ request }) => { await request.post("/__test/login?account_id=2"); });

test("whole question preserves shared context, complete available answer and exact verification binding", async ({ page }, testInfo) => {
  await queue(page);
  let request: Record<string, unknown> | undefined;
  await page.route("**/classifications/questions/*/verify", route => { request = route.request().postDataJSON(); return route.fulfill({ json: { revision_id: 8, current_revision_id: 8, verification_count: 3 } }); });
  await page.goto("/curator/classifications");
  await expect(page.getByText("Company case shared by both parts.", { exact: true })).toBeVisible();
  await expect(page.getByText("Revenue is 100.", { exact: true })).toBeVisible();
  await expect(page.getByText("Revenue Chapter → Revenue Topic").first()).toBeVisible();
  await expect(page.getByText("Topic labels verified by 2 students")).toBeVisible();
  await expect(page.getByText("Extraction-quality review is separate.")).toBeVisible();
  await page.getByRole("button", { name: "Verify the current published mapping" }).click();
  await expect(page.getByRole("status")).toContainText("Revision operation saved");
  expect(request?.expected_suggestion_revision_id).toBe(7);
  expect(request?.expected_publication_revision_id).toBe(8);
  expect(request?.idempotency_key).toBeTruthy();
  await page.screenshot({ path: `/tmp/phase5-classification-${testInfo.project.name}.png`, fullPage: true });
});

test("draft blind benchmark hides model labels until submission and records independent evidence", async ({ page }) => {
  await queue(page, { ...item, experimental: true, publication_ready: false, readiness_blockers: [{ code: "draft", message: "Draft inputs require review" }] });
  let request: Record<string, unknown> | undefined;
  await page.route("**/classifications/11/review", route => { request = route.request().postDataJSON(); return route.fulfill({ json: { revision_id: 12, current_revision_id: 8, verification_count: 2, status: "benchmark", pending: true } }); });
  await page.goto("/curator/classifications?blind=true");
  await expect(page.getByText("Model confidence:", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Revision history and correction differences" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Submit correction or dispute" })).toHaveCount(0);
  await page.getByRole("button", { name: "Choose primary label" }).click();
  await page.getByRole("button", { name: /Revenue Topic/ }).click();
  await page.getByLabel("Review evidence or correction reason").fill("Independent revenue classification from the full question.");
  await page.getByLabel("I reviewed the complete question, available answer and every part label").check();
  await page.getByRole("button", { name: "Confirm complete classification revision" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Blind benchmark saved" })).toBeVisible();
  await expect(page.getByLabel("Blind benchmark mode")).not.toBeChecked();
  await expect(page.getByText("Model confidence:", { exact: false })).toBeVisible();
  expect(request?.blind).toBe(true);
  expect(request?.mappings).toEqual([expect.objectContaining({ part_id: mapping.part_id, primary_node_id: "topic.1", outcome: "matched" })]);
  await expect(page.getByText("Topic labels verified by 2 students")).toBeVisible();
});

test("stale review stays visible and retries reuse the idempotency key", async ({ page }) => {
  await queue(page);
  const requests: Record<string, unknown>[] = [];
  await page.route("**/classifications/11/review", route => { requests.push(route.request().postDataJSON()); return route.fulfill({ status: 409, json: { detail: { code: "stale_revision", message: "Publication changed", current_revision_id: 9 } } }); });
  await page.goto("/curator/classifications");
  await page.getByLabel("Review evidence or correction reason").fill("Checked all part labels against full context.");
  await page.getByLabel("I reviewed the complete question, available answer and every part label").check();
  const submit = page.getByRole("button", { name: "Confirm complete classification revision" });
  await submit.evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  await expect(page.getByRole("alert")).toContainText("Publication changed");
  expect(requests).toHaveLength(1);
  await submit.click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[0].idempotency_key).toBe(requests[1].idempotency_key);
  await expect(page.getByText("Company case shared by both parts.", { exact: true })).toBeVisible();
  await expect(page.getByText("Revision operation saved.")).toHaveCount(0);
  await page.route("**/api/v1/curate/classifications?*", route => route.fulfill({ json: [{ ...item,
    publication_revision_id: 9, verification_count: 1,
    published_mappings: [{ ...mapping, outcome: "none_fits", primary_node_id: null }] }] }));
  await page.getByRole("button", { name: "Refresh current revision for comparison" }).click();
  await expect(page.getByRole("heading", { name: "Current publication 9", exact: true })).toBeVisible();
  await expect(page.getByLabel("I reviewed the complete question, available answer and every part label")).not.toBeChecked();
  await expect(page.getByLabel("Review evidence or correction reason")).toHaveValue("Checked all part labels against full context.");
  await page.getByLabel("I reviewed the complete question, available answer and every part label").check();
  await submit.click();
  await expect.poll(() => requests.length).toBe(3);
  expect(requests[2].expected_publication_revision_id).toBe(9);
  expect(requests[2].idempotency_key).not.toBe(requests[1].idempotency_key);
});
