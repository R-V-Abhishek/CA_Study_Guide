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
  await page.getByRole("button", { name: "Verify current labels" }).click();
  await expect(page.getByRole("status")).toContainText("Revision operation saved");
  expect(request?.expected_suggestion_revision_id).toBe(7);
  expect(request?.expected_publication_revision_id).toBe(8);
  expect(request?.idempotency_key).toBeTruthy();
  await page.screenshot({ path: `/tmp/phase5-classification-${testInfo.project.name}.png`, fullPage: true });
});

for (const width of [390, 768, 1280, 1440]) {
  test(`review workspace preserves complete content and edits at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await queue(page);
    await page.goto("/curator/classifications");
    await expect(page.getByText("Company case shared by both parts.", { exact: true })).toBeVisible();
    await page.getByLabel("Review evidence or correction reason").fill("Source comparison stays attached to the current review.");
    if (width < 768) {
      await page.getByRole("tab", { name: "Answer", exact: true }).click();
      await expect(page.getByText("Revenue is 100.", { exact: true })).toBeVisible();
      await page.getByRole("tab", { name: "Labels", exact: true }).click();
      await expect(page.getByText("Revenue Chapter → Revenue Topic").first()).toBeVisible();
      await page.getByRole("tab", { name: "Question", exact: true }).click();
    } else await expect(page.getByText("Revenue is 100.", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Review evidence or correction reason")).toHaveValue("Source comparison stays attached to the current review.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/phase7-curator-${width}-${testInfo.project.name}.png`, fullPage: true });
  });
}

test("review separators support keyboard resizing without publishing", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await queue(page);
  await page.goto("/curator/classifications");
  const separator = page.getByRole("separator", { name: "Resize queue pane" });
  await separator.focus();
  await page.keyboard.press("ArrowRight");
  await expect(separator).toHaveAttribute("aria-valuenow", "280");
  await page.getByLabel("Review evidence or correction reason").fill("Alt shortcuts remain inert while editing.");
  await page.keyboard.press("Alt+j");
  await expect(page.getByRole("button", { name: "Publish reviewed labels" })).toBeDisabled();
  await page.getByRole("heading", { name: "Review questions", exact: true }).click();
  await page.keyboard.press("Alt+l");
  await expect(page.locator("#review-Labels")).toBeFocused();
});

test("source filters use the acquired document type rather than its broad family", async ({ page }) => {
  await queue(page, { ...item, doc_type_id: "model_question" });
  await page.goto("/curator/classifications");
  await page.getByLabel("Source type", { exact: true }).selectOption("model_question");
  await expect(page).toHaveURL(/source=model_question/);
  await expect(page.getByText("Company case shared by both parts.", { exact: true })).toBeVisible();
});

test("readiness links select the exact affected question and scope changes clear that selection", async ({ page }) => {
  await page.route("**/api/v1/curate/classifications?**", route => route.fulfill({ json: [{ ...item, question_id: "scope:other", suggestion_revision_id: 12, question: { ...item.question, question_id: "scope:other", display_label: "Q2", common_stem: "An unselected question shared case." } }, item] }));
  await page.goto(`/curator/classifications?question_id=${encodeURIComponent(item.question_id)}`);
  await expect(page.getByText("Company case shared by both parts.", { exact: true })).toBeVisible();
  await expect(page.getByText("An unselected question shared case.", { exact: true })).toHaveCount(0);
  await page.getByLabel("Source type", { exact: true }).selectOption("model");
  await expect(page).not.toHaveURL(/question_id=/);
});

test("classification opens complete original pages and restores source-button focus", async ({ page }) => {
  await queue(page);
  await page.route("**/api/v1/extraction/revisions/2", route => route.fulfill({ json: { id: 2, source_documents: [{ id: 10, sha256: "a".repeat(64), page_count: 2 }], questions: [], quality: { issues: [] } } }));
  await page.route("**/api/v1/extraction/documents/10/pages/*", route => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><text x="20" y="30">Original official source fixture</text></svg>' }));
  await page.goto("/curator/classifications");
  const source = page.getByRole("button", { name: "View source", exact: true });
  await source.click();
  await expect(page.getByRole("dialog", { name: "Original source evidence" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Original document 10, page 1" })).toBeVisible();
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(page.getByRole("img", { name: "Original document 10, page 2" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(source).toBeFocused();
});

test("original PDF opens as an authenticated blob and failures retain source and question", async ({ page }) => {
  await queue(page);
  await page.route("**/api/v1/extraction/revisions/2", route => route.fulfill({ json: { id: 2, source_documents: [{ id: 10, sha256: "a".repeat(64), page_count: 2 }], questions: [], quality: { issues: [] } } }));
  await page.route("**/api/v1/extraction/documents/10/pages/*", route => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><text x="20" y="30">Original source</text></svg>' }));
  await page.route("**/api/v1/extraction/documents/10/pdf", route => route.fulfill({ status: 404, json: { detail: "Original PDF is unavailable" } }));
  await page.goto("/curator/classifications");
  await page.getByRole("button", { name: "View source", exact: true }).click();
  await page.getByRole("button", { name: "Open PDF", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Original PDF is unavailable");
  await expect(page.getByRole("img", { name: "Original document 10, page 1" })).toBeVisible();
  await page.route("**/api/v1/extraction/documents/10/pdf", route => route.fulfill({ contentType: "application/pdf", body: "%PDF-1.4\n%%EOF" }));
  const opened = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Open PDF", exact: true }).click();
  const pdf = await opened;
  await expect(page.getByRole("link", { name: "Open PDF", exact: true })).toHaveAttribute("href", /^blob:/);
  await pdf.close();
  await page.getByRole("button", { name: "Close source", exact: true }).click();
  await expect(page.getByText("Company case shared by both parts.", { exact: true })).toBeVisible();
});

test("draft blind benchmark hides model labels until submission and records independent evidence", async ({ page }) => {
  await queue(page, { ...item, experimental: true, publication_ready: false, readiness_blockers: [{ code: "draft", message: "Draft inputs require review" }] });
  let request: Record<string, unknown> | undefined;
  await page.route("**/classifications/11/review", route => { request = route.request().postDataJSON(); return route.fulfill({ json: { revision_id: 12, current_revision_id: 8, verification_count: 2, status: "benchmark", pending: true } }); });
  await page.goto("/curator/classifications?blind=true");
  await expect(page.getByText("Model confidence:", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Revision history and correction differences" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Submit correction" })).toHaveCount(0);
  await page.getByRole("button", { name: "Change primary" }).click();
  await page.getByRole("button", { name: /Revenue Topic/ }).click();
  await page.getByLabel("Review evidence or correction reason").fill("Independent revenue classification from the full question.");
  await page.getByLabel("I reviewed the complete question, available answer and every part label").check();
  await page.getByRole("button", { name: "Save blind review" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Blind benchmark saved" })).toBeVisible();
  await expect(page.getByLabel("Blind benchmark mode")).not.toBeChecked();
  await page.getByText("Model evidence and alternatives", { exact: true }).click();
  await expect(page.getByText("Model confidence:", { exact: false })).toBeVisible();
  expect(request?.blind).toBe(true);
  expect(request?.mappings).toEqual([expect.objectContaining({ part_id: mapping.part_id, primary_node_id: "topic.1", outcome: "matched" })]);
  await expect(page.getByText("Topic labels verified by 2 students")).toBeVisible();
});

test("concurrent review opens comparison, retains evidence and requires fresh confirmation", async ({ page }) => {
  await queue(page);
  const requests: Record<string, unknown>[] = [];
  await page.route("**/classifications/11/review", route => { requests.push(route.request().postDataJSON()); return route.fulfill({ status: 409, json: { detail: { code: "stale_revision", message: "Publication changed", current_revision_id: 9 } } }); });
  await page.goto("/curator/classifications");
  await page.getByLabel("Review evidence or correction reason").fill("Checked all part labels against full context.");
  await page.getByLabel("I reviewed the complete question, available answer and every part label").check();
  const submit = page.getByRole("button", { name: "Publish reviewed labels" });
  await submit.evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  await expect(page.getByRole("alert")).toContainText("Publication changed");
  expect(requests).toHaveLength(1);
  await expect(page.getByRole("dialog", { name: "This review has changed" })).toBeVisible();
  await expect(page.getByLabel("I reviewed the complete question, available answer and every part label")).not.toBeChecked();
  await expect(submit).toBeDisabled();
  await page.route("**/api/v1/curate/classifications?*", route => route.fulfill({ json: [{ ...item,
    publication_revision_id: 9, verification_count: 1,
    published_mappings: [{ ...mapping, outcome: "none_fits", primary_node_id: null }] }] }));
  await page.getByRole("button", { name: "Refresh current revision for comparison" }).click();
  await expect(page.getByRole("heading", { name: "Current publication", exact: true })).toBeVisible();
  await expect(page.getByLabel("I reviewed the complete question, available answer and every part label")).not.toBeChecked();
  await expect(page.getByLabel("Review evidence or correction reason")).toHaveValue("Checked all part labels against full context.");
  await page.getByLabel("I reviewed the complete question, available answer and every part label").check();
  await submit.click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].expected_publication_revision_id).toBe(9);
  expect(requests[1].idempotency_key).not.toBe(requests[0].idempotency_key);
});

test("a background refresh clears stale publication confirmation while retaining the proposed labels and reason", async ({ page }) => {
  let current = item;
  await page.route("**/api/v1/curate/classifications?**", route => route.fulfill({ json: [current] }));
  await page.goto("/curator/classifications");
  await page.getByLabel("Outcome (a)", { exact: true }).selectOption("none_fits");
  const reason = page.getByLabel("Review evidence or correction reason");
  await reason.fill("This part does not fit the available descriptor after source comparison.");
  const confirmation = page.getByLabel("I reviewed the complete question, available answer and every part label");
  await confirmation.check();
  current = { ...item, publication_revision_id: 9, verification_count: 1 };
  // Matching profile updates invalidate shared queries through the existing auth-shell event.
  await page.evaluate(() => window.dispatchEvent(new Event("caf-profile-changed")));
  await expect(page.getByRole("status").filter({ hasText: "The current publication changed" })).toBeVisible();
  await expect(confirmation).not.toBeChecked();
  await expect(reason).toHaveValue("This part does not fit the available descriptor after source comparison.");
  await expect(page.getByLabel("Outcome (a)", { exact: true })).toHaveValue("none_fits");
  await expect(page.getByRole("button", { name: "Publish reviewed labels" })).toBeDisabled();
});
