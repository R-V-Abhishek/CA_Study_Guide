import { test, expect } from "./fixtures";
import type { ReadinessSummary } from "../../packages/api-client/src/readiness";

const initial: ReadinessSummary = {
  target_attempt_id: "2027-05", taxonomy_version_id: 3,
  papers: [{ paper_id: "s2023.P1", name: "Financial Reporting", blocker_count: 1, published_roots: 0, expected_slots: null }],
  tasks: [{ id: "binding", paper_id: "s2023.P1", stage: 3, stage_name: "Applicability and attempt binding", blocker: "binding_review_pending", evidence: ["Prescribed edition applicability awaits authentic review."], required_role: "administrator", next_action: { label: "Inspect syllabus evidence", href: "/curator/textbooks" }, affected_records: [{ kind: "binding", id: "2027-05:3", revision: "a".repeat(64) }] }],
  bindings: [{ target_attempt_id: "2027-05", taxonomy_version_id: 3, status: "pending", reviewed_by: null, expected_hash: "a".repeat(64) }],
  inventory: [{ paper_id: "s2023.P1", attempt_id: "2026-05", taxonomy_version_id: 3, source_family: "past_exam", expected_slots: null, inventory_reviewed: false, expected_hash: "c".repeat(64) }],
  priors: [], source_evidence: [{ kind: "textbook_span", span_id: 4, sha256: "b".repeat(64) }], history: [],
};

test.beforeEach(async ({ request }) => { await request.post("/__test/login?account_id=3"); });

test("readiness preserves unknown inventory and exposes exact source evidence tasks", async ({ page }) => {
  await page.route("**/api/v1/admin/readiness?**", route => route.fulfill({ json: initial }));
  await page.goto("/curator/readiness");
  await expect(page.getByText("Unknown — inventory review required")).toBeVisible();
  await page.getByRole("button", { name: "View evidence" }).click();
  await expect(page.getByRole("dialog", { name: "Readiness evidence" })).toBeVisible();
  await expect(page.getByText("Prescribed edition applicability awaits authentic review.")).toBeVisible();
  await page.getByRole("button", { name: "Close evidence" }).click();
  await page.getByText("Expected inventory (1)", { exact: true }).click();
  await page.getByRole("button", { name: "Review expected inventory" }).click();
  await expect(page.getByLabel("Expected source slots (leave blank if unknown)")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Record reviewed decision" })).toBeDisabled();
});

test("readiness conflicts retain edits and require refreshed revision and confirmation", async ({ page }) => {
  let current = initial;
  await page.route("**/api/v1/admin/readiness?**", route => route.fulfill({ json: current }));
  const requests: Record<string, unknown>[] = [];
  await page.route("**/api/v1/admin/readiness/bindings", route => {
    requests.push(route.request().postDataJSON());
    return requests.length === 1 ? route.fulfill({ status: 409, json: { detail: { message: "Attempt binding changed", current_hash: "d".repeat(64) } } }) : route.fulfill({ json: { record_id: "2027-05:3", expected_hash: "e".repeat(64), audit_id: 9, actor_id: 3, corpus_generation: 2 } });
  });
  await page.goto("/curator/readiness");
  await page.getByText("Attempt bindings (1)", { exact: true }).click();
  await page.getByRole("button", { name: "Review attempt binding" }).click();
  await page.getByLabel("Reviewed textbook source context 1").check();
  const reason = page.getByLabel("Review evidence and reason");
  await reason.fill("Compared the official prescribed edition and attempt applicability.");
  const confirmation = page.getByLabel("I reviewed the current record, proposed decision and cited approved source evidence.");
  await confirmation.check();
  await page.getByRole("button", { name: "Record reviewed decision" }).click();
  await expect(page.getByRole("alert")).toContainText("Attempt binding changed");
  await expect(reason).toHaveValue("Compared the official prescribed edition and attempt applicability.");
  await expect(confirmation).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Record reviewed decision" })).toBeDisabled();
  current = { ...initial, bindings: [{ ...initial.bindings[0], expected_hash: "d".repeat(64) }] };
  await page.getByRole("button", { name: "Refresh current record for comparison" }).click();
  await confirmation.check();
  await page.getByRole("button", { name: "Record reviewed decision" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Reviewed decision recorded" })).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[0].expected_hash).toBe("a".repeat(64));
  expect(requests[1].expected_hash).toBe("d".repeat(64));
  expect(requests[1].source_evidence).toEqual(initial.source_evidence);
  expect(requests[1].idempotency_key).not.toBe(requests[0].idempotency_key);
  expect(requests[1]).not.toHaveProperty("actor_id");
});
