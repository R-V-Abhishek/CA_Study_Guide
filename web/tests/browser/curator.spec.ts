import { test, expect, type Page } from "./fixtures";
import type { components } from "../../packages/api-client/src/generated";
test.beforeEach(async ({ request }) => { await request.post('/__test/login?account_id=3'); });

type QueueItem = components["schemas"]["CuratorQueueItem"];
type Paper = components["schemas"]["PaperSummary"];
const papers: Paper[] = [
  { id: "fixture.FR", code: "FR", name: "Fixture Financial Reporting", group_no: 1, total_subtopics: 3, completed_subtopics: 0, raw_progress_pct: 0, weighted_coverage_pct: 0, average_importance: 0, revision_due_count: 0, weak_topic_count: 0 },
  { id: "fixture.DT", code: "DT", name: "Fixture Direct Tax", group_no: 2, total_subtopics: 1, completed_subtopics: 0, raw_progress_pct: 0, weighted_coverage_pct: 0, average_importance: null, revision_due_count: 0, weak_topic_count: 0 },
];
const metadata: components["schemas"]["Metadata"] = {
  taxonomy_version: "fixture", scoring_version: "fixture-scoring", api_version: "fixture-api", backend_revision: "fixture-backend",
  target_attempt: "2026-05", score_run_id: 12, score_run_computed_at: "2026-10-01T00:00:00Z", score_run: { id: 12, version: "fixture-scoring", target_attempt_id: "2026-05", computed_at: "2026-10-01T00:00:00Z" }, ingestion_coverage: [],
};
function unit(id: number, overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    unit_id: id, publication_ready: true, document_id: 1, attempt_id: "2024-05", paper_id: "fixture.FR", doc_type_id: "exam", label_path: `Q${id}.a`, display_label: `${id}(a)`, is_benchmark: false,
    marks: 0, question_text: `Fixture question ${id}`, answer_text: `Fixture answer ${id}`, bucket: "A",
    primary_suggestion: { node_id: `fixture.node.${id}`, node_name: `Real recommendation ${id}`, chapter: { id: "fixture.chapter", name: "Real Chapter" }, topic: { id: "fixture.topic", name: "Real Topic" }, subtopic: { id: `fixture.node.${id}`, name: `Real recommendation ${id}` }, justification: "Actual fixture justification", gist: null, alternatives: [] }, secondary_suggestions: [], ...overrides,
  };
}
async function interceptCommon(page: Page) {
  await page.route("**/api/v1/papers", route => route.fulfill({ json: papers }));
  await page.route("**/api/v1/meta", route => route.fulfill({ json: metadata }));
}

test.describe("curator controlled responses", () => {
  test.beforeEach(async ({ page }) => { await interceptCommon(page); });

  test("slow, empty and unavailable queues remain distinct", async ({ page }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/api/v1/curate/queue**", async route => { await gate; await route.fulfill({ json: [] }); });
    await page.goto("/curator/queue");
    await expect(page.getByRole("status")).toHaveText("Loading review queue…");
    release();
    await expect(page.getByRole("heading", { name: "Queue Empty" })).toBeVisible();
    await page.unroute("**/api/v1/curate/queue**");
    await page.route("**/api/v1/curate/queue**", route => route.fulfill({ status: 503, json: { detail: "Queue unavailable" } }));
    await page.reload();
    await expect(page.getByRole("alert")).toContainText("Queue unavailable");
    await expect(page.getByRole("heading", { name: "Queue Empty" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Catalogue" })).toBeVisible();
  });

  test("combined filters use returned IDs and URL reload/back state", async ({ page }) => {
    const requests: string[] = [];
    await page.route("**/api/v1/curate/queue**", route => {
      const url = new URL(route.request().url()); requests.push(url.search);
      const items = [unit(1), unit(2, { bucket: "B", paper_id: "fixture.DT" }), unit(3, { bucket: "D", paper_id: "fixture.DT" })].filter(item => (!url.searchParams.has("bucket") || item.bucket === url.searchParams.get("bucket")) && (!url.searchParams.has("paper_id") || item.paper_id === url.searchParams.get("paper_id")));
      return route.fulfill({ json: items });
    });
    await page.goto("/curator/queue");
    await page.getByRole("combobox", { name: "Bucket", exact: true }).selectOption("B");
    await page.getByRole("combobox", { name: "Paper", exact: true }).selectOption("fixture.DT");
    await expect(page).toHaveURL(/bucket=B.*paper=fixture.DT/);
    await expect(page.getByText("Fixture question 2", { exact: true })).toBeVisible();
    await expect.poll(() => requests.at(-1)).toContain("bucket=B");
    await expect.poll(() => requests.at(-1)).toContain("paper_id=fixture.DT");
    await page.reload();
    await expect(page.getByRole("combobox", { name: "Paper", exact: true })).toHaveValue("fixture.DT");
    await page.getByRole("combobox", { name: "Bucket", exact: true }).selectOption("A");
    await expect(page.getByRole("heading", { name: "No units match these filters" })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole("combobox", { name: "Bucket", exact: true })).toHaveValue("B");
    await expect(page.getByText("Fixture question 2", { exact: true })).toBeVisible();
    await page.getByRole("combobox", { name: "Bucket", exact: true }).selectOption("D");
    await expect(page.getByText("Fixture question 3", { exact: true })).toBeVisible();
    await expect.poll(() => requests.at(-1)).toContain("bucket=D");
  });

  test("failed decisions retain item, guard duplicates and never claim acceptance", async ({ page }) => {
    await page.route("**/api/v1/curate/queue**", route => route.fulfill({ json: [unit(1), unit(2)] }));
    let count = 0; let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/api/v1/curate/units/*/decision", async route => { count++; await gate; await route.fulfill({ status: 500, json: { detail: "Decision not accepted" } }); });
    await page.goto("/curator/queue");
    const accept = page.getByRole("button", { name: "[A] Accept Recommendation", exact: true });
    await accept.evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
    await expect(page.getByRole("button", { name: "Saving decision…" })).toBeDisabled();
    await expect.poll(() => count).toBe(1);
    await expect(page.getByText("Fixture question 1", { exact: true })).toBeVisible();
    release();
    await expect(page.getByRole("alert")).toContainText("Decision not accepted");
    await expect(page.getByText("Fixture question 1", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "[A] Accept Recommendation", exact: true })).toBeEnabled();
    await expect(page.getByText("1 / 2", { exact: true })).toBeVisible();
  });

  test("successful decisions preserve the next valid selection without skipping", async ({ page }) => {
    let items = [unit(1), unit(2), unit(3)];
    await page.route("**/api/v1/curate/queue**", route => route.fulfill({ json: items }));
    await page.route("**/api/v1/curate/units/*/decision", route => {
      const id = Number(route.request().url().match(/units\/(\d+)\//)![1]);
      items = items.filter(item => item.unit_id !== id);
      return route.fulfill({ json: { decision_id: id, action: "accept", unit_fingerprint: `fixture-${id}` } satisfies components["schemas"]["CuratorDecisionResult"] });
    });
    await page.goto("/curator/queue");
    await page.getByRole("button", { name: "Next unit", exact: true }).click();
    await expect(page.getByText("Fixture question 2", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "[A] Accept Recommendation", exact: true }).click();
    await expect(page.getByText("Fixture question 3", { exact: true })).toBeVisible();
    await expect(page.getByText("2 / 2", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "[A] Accept Recommendation", exact: true }).click();
    await expect(page.getByText("Fixture question 1", { exact: true })).toBeVisible();
    await expect(page.getByText("1 / 1", { exact: true })).toBeVisible();
  });

  test("long answers, null answers, ancestry and zero marks are honest and accessible", async ({ page }) => {
    const answer = "Full returned answer.\n".repeat(500) + "FINAL ANSWER SENTINEL";
    await page.route("**/api/v1/curate/queue**", route => route.fulfill({ json: [unit(1, { answer_text: answer }), unit(2, { answer_text: null })] }));
    await page.goto("/curator/queue");
    await expect(page.getByText("Real Chapter → Real Topic → Real recommendation 1", { exact: true })).toBeVisible();
    await expect(page.getByText(/· 0 Marks/)).toBeVisible();
    const region = page.getByRole("region", { name: "Answer text", exact: true });
    await expect(region).toContainText("FINAL ANSWER SENTINEL");
    await expect(region).toHaveAttribute("tabindex", "0");
    await page.getByRole("button", { name: "Expand full answer", exact: true }).click();
    await expect(page.getByRole("button", { name: "Collapse answer", exact: true })).toHaveAttribute("aria-expanded", "true");
    await expect.poll(() => region.evaluate(element => element.scrollHeight <= element.clientHeight + 1)).toBe(true);
    await page.getByRole("button", { name: "Next unit", exact: true }).click();
    await expect(page.getByText("Answer unavailable", { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Answer text", exact: true })).toHaveCount(0);
  });

  test("diagnostics show tested API identities and exclude route secrets", async ({ page }) => {
    await page.route("**/api/v1/curate/queue**", route => route.fulfill({ json: [] }));
    await page.goto("/curator/queue?token=PRIVATE_TOKEN&notes=PRIVATE_NOTES");
    await page.getByRole("button", { name: "Diagnostics", exact: true }).click();
    const info = JSON.parse(await page.getByRole("textbox", { name: "Diagnostics data", exact: true }).inputValue());
    expect(info.backend).toEqual({ api_version: "fixture-api", revision: "fixture-backend" });
    expect(info.frontend.app).toBe("curator"); expect(info.frontend.revision).toBeTruthy();
    expect(info.route).toBe("/queue"); expect(info.target_attempt).toBe("2026-05"); expect(info.score_run.id).toBe(12);
    expect(JSON.stringify(info)).not.toContain("PRIVATE_TOKEN"); expect(JSON.stringify(info)).not.toContain("PRIVATE_NOTES");
  });

  test("other curator pages report failed loads with usable navigation", async ({ page }) => {
    test.setTimeout(60_000);
    await page.route("**/api/v1/curate/documents**", route => route.fulfill({ status: 503, json: { detail: "Documents unavailable" } }));
    await page.route("**/api/v1/tree**", route => route.fulfill({ status: 503, json: { detail: "Taxonomy unavailable" } }));
    await page.route("**/api/v1/system/health", route => route.fulfill({ status: 503, json: { detail: "Health unavailable" } }));
    await page.route("**/api/v1/system/backups", route => route.fulfill({ status: 503, json: { detail: "Backups unavailable" } }));
    const uncaught: string[] = []; page.on("pageerror", error => uncaught.push(error.message));
    for (const [route, message] of [["documents", "Documents unavailable"], ["bulk", "Documents unavailable"], ["taxonomy", "Taxonomy unavailable"], ["system", "Health unavailable"]]) {
      await page.goto(`/curator/${route}`);
      await expect(page.getByRole("alert").filter({ hasText: message })).toBeVisible();
      await expect(page.getByRole("link", { name: "Review Queue", exact: true })).toBeVisible();
    }
    await expect(page.getByText("healthy", { exact: true })).toHaveCount(0);
    expect(uncaught).toEqual([]);
  });

  test("document, bulk and recompute failures remain visibly unsuccessful", async ({ page }) => {
    const document: components["schemas"]["CuratorDocument"] = {
      id: 1, sha256: "b".repeat(64), title: "Fixture document", scheme_id: "fixture", attempt_id: null, paper_id: null,
      doc_type_id: null, series: null, part: null, catalog_status: "inferred", extract_status: "ok", page_count: null,
      bytes: 0, origin: "manual", created_at: null, provenance_status: "unresolved",
    };
    await page.route("**/api/v1/curate/documents**", route => route.request().method() === "GET"
      ? route.fulfill({ json: [document] })
      : route.fulfill({ status: 500, json: { detail: "Document action failed" } }));
    await page.route("**/api/v1/curate/intel/recompute*", route => route.fulfill({ status: 500, json: { detail: "Recompute failed" } }));
    await page.route("**/api/v1/system/health", route => route.fulfill({ json: { status: "healthy", evaluated_at: "2026-10-01T00:00:00Z", alarms: [] } satisfies components["schemas"]["SystemHealth"] }));
    await page.route("**/api/v1/system/backups", route => route.fulfill({ json: { count: 0, backups: [] } satisfies components["schemas"]["BackupList"] }));
    await page.goto("/curator/documents");
    await expect(page.getByText("Unavailable", { exact: true })).toHaveCount(4);
    await page.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Document action failed");
    await expect(page.getByText("inferred", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Reject", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Document action failed");
    await page.goto("/curator/bulk");
    await page.getByRole("button", { name: "Accept All Bucket A Units", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Document action failed");
    await expect(page.getByText(/Successfully published/)).toHaveCount(0);
    await page.goto("/curator/system");
    await page.getByRole("button", { name: "Trigger L5 Recompute", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Recompute failed");
    await expect(page.getByText(/Score recompute completed/)).toHaveCount(0);
    await expect(page.getByText("No backup snapshots returned.", { exact: true })).toBeVisible();
  });
});

test.describe("curator disposable database integration", () => {
  test.beforeEach(async ({ request }) => { expect((await request.post("/__test/reset")).ok()).toBeTruthy(); await request.post('/__test/login?account_id=3'); });

  test("direct curator routes render actual API contracts without uncaught errors", async ({ page }) => {
    const uncaught: string[] = []; page.on("pageerror", error => uncaught.push(error.message));
    for (const [route, heading] of [["queue", "Review Queue"], ["documents", "Document Catalogue"], ["bulk", "Bulk Accept — Bucket A Consensus"], ["taxonomy", "Taxonomy Explorer"], ["system", "System Health & Ops Monitor"]]) {
      await page.goto(`/curator/${route}`); await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
      await expect(page.getByRole("link", { name: "Review Queue", exact: true })).toBeVisible();
      await expect(page.getByRole("alert")).toHaveCount(0);
    }
    expect(uncaught).toEqual([]);
  });

  test("accepted decisions persist across reload and remove only the accepted queue unit", async ({ page, request }) => {
    const fixture = await (await request.get("/__test/fixture")).json() as { unit_id: number; nodes: Array<{ id: string; name: string }> };
    await page.goto("/curator/queue");
    await expect(page.getByRole("region", { name: "Answer text", exact: true })).toContainText("FINAL ANSWER SENTINEL");
    await expect(page.getByText(fixture.nodes[0].name, { exact: true })).toBeVisible();
    const response = page.waitForResponse(res => res.url().includes(`/curate/units/${fixture.unit_id}/decision`) && res.request().method() === "POST");
    await page.getByRole("button", { name: "[A] Accept Recommendation", exact: true }).click();
    expect((await response).ok()).toBeTruthy();
    await expect(page.getByRole("heading", { name: "Queue Empty", exact: true })).toBeVisible();
    await page.reload(); await expect(page.getByRole("heading", { name: "Queue Empty", exact: true })).toBeVisible();
    const queue = await (await request.get("/api/v1/curate/queue")).json() as QueueItem[];
    expect(queue.some(item => item.unit_id === fixture.unit_id)).toBe(false);
  });
});
