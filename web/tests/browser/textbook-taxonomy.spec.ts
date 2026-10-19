import { test, expect, type Page } from "./fixtures";
import type { TaxonomyVersion, TextbookNode, TextbookSource, TextbookDescriptor, TaxonomyDescriptor, TaxonomyReleaseReport } from "../../packages/api-client/src/taxonomy";

const version: TaxonomyVersion = { version_id: "textbook-fixture", taxonomy_version_id: 2, target_attempt: "2027-05", status: "draft", manifest_hash: "c".repeat(64), approved_by: null, activated_at: null };
const source: TextbookSource = { artifact_id: "official.fixture", edition: "January 2026", applicable_attempts: ["2026-01"], download_url: "https://resource.cdn.icai.org/fixture.pdf", landing_url: "https://www.icai.org/fixture", fallback: true, target_applicability: "provision_review_required", availability: "verified", pdf_page_start: 12, pdf_page_end: 16, review_status: "pending", instrument: "Income-tax Act, 1961" };
const labels = ["Paper Four", "Official Module One", "Official Chapter", "Official Unit", "Income concept", "Tax concept"];
function hierarchy(depth = 0): TextbookNode {
  const levels = ["paper", "module", "chapter", "unit", "topic", "subtopic"];
  return { id: `fresh.${depth}`, paper_id: "P4", parent_id: depth ? `fresh.${depth - 1}` : null, level: levels[depth], name: labels[depth], seq: 1, heading_origin: depth === 5 ? "app_authored" : "official", source_review_status: "pending", descriptor_revision: depth === 5 ? 1 : null, descriptor_approved: false, eligible: false, breadcrumbs: labels.slice(0, depth + 1).map((name, index) => ({ id: `fresh.${index}`, name, level: levels[index] })), sources: [source], children: depth < 5 ? [hierarchy(depth + 1)] : [] };
}
const descriptor: TextbookDescriptor = { revision: 1, definition: "A fixture definition from the textbook.", terminology: ["Income-tax Act, 1961"], instrument_references: ["Income-tax Act, 1961"], edition: "January 2026", source_ambiguities: [], inclusion: ["Included fixture concepts"], exclusion: ["Excluded fixture concepts"], nearby_distinctions: ["A nearby concept differs here"], approved: false, source_spans: [{ artifact_id: source.artifact_id, pdf_page_start: source.pdf_page_start, pdf_page_end: source.pdf_page_end, review_status: source.review_status }] };

test("index heading evidence remains distinct until an authored explanation creates a new revision", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2");
  await routes(page);
  let current: TaxonomyDescriptor = { revision: 1, status: "index_derived_draft_requires_review", core_concept: "Original index heading", scope: "Module / Original index heading", terminology: ["Original index heading"], approved: false, applicability_status: "source_attempts_only_target_release_not_approved", source_edition: source.edition, applicable_attempts: source.applicable_attempts, note: "Index heading evidence only; no statutory interpretation or release approval is inferred." };
  await page.route("**/api/v1/taxonomy/nodes/*/descriptor?**", route => route.fulfill({ json: current }));
  let saved: Record<string, unknown> | undefined;
  await page.route("**/api/v1/taxonomy/nodes/*/descriptor", route => {
    saved = route.request().postDataJSON();
    current = { ...descriptor, definition: "Authored explanation from cited source", revision: 2 };
    return route.fulfill({ json: { revision: 2, approved: false } });
  });
  await page.goto("/curator/textbooks"); await selectLeaf(page, true);
  await page.getByRole("tab", { name: "Descriptor", exact: true }).click();
  const evidence = page.getByRole("region", { name: "Index heading evidence" });
  await expect(evidence).toContainText("Original index heading");
  await expect(evidence).toContainText("A textbook explanation has not been authored or approved.");
  await expect(evidence.getByRole("link", { name: "Textbook PDF, pages 12–16" })).toHaveAttribute("href", `${source.download_url}#page=12`);
  await expect(page.getByRole("button", { name: "Approve reviewed descriptor revision" })).toHaveCount(0);
  await page.getByRole("button", { name: "Edit descriptor", exact: true }).click();
  await expect(page.getByLabel("Concept definition", { exact: true })).toHaveValue("");
  await expect(page.getByRole("button", { name: "Save new descriptor revision" })).toBeDisabled();
  await page.getByLabel("Concept definition", { exact: true }).fill("Authored explanation from cited source");
  await page.getByRole("button", { name: "Save new descriptor revision" }).click();
  await expect(page.getByText("Revision 2 · Review pending")).toBeVisible();
  expect(saved?.source_spans).toEqual(descriptor.source_spans);
  expect(saved?.definition).toBe("Authored explanation from cited source");
  expect(saved).not.toHaveProperty("core_concept");
});
const report: TaxonomyReleaseReport = { version_id: version.version_id, manifest_hash: version.manifest_hash, status: "draft", node_count: 6, eligible_count: 0, source_count: 1, unresolved_sources: ["official.fixture"], unreviewed_descriptors: ["fresh.5"], activation_ready: false, blockers: ["Source applicability unresolved"], legacy_progress_count: 2, legacy_note_count: 1 };
async function routes(page: Page) {
  await page.route("**/api/v1/taxonomy/versions", route => route.fulfill({ json: [version] }));
  await page.route("**/api/v1/taxonomy/versions/*/tree", route => route.fulfill({ json: [hierarchy()] }));
  await page.route("**/api/v1/taxonomy/nodes/*/descriptor?**", route => route.fulfill({ json: descriptor }));
  await page.route("**/api/v1/taxonomy/nodes/*/history?**", route => route.fulfill({ json: { node_id: "fresh.5", records: [{ node_id: "legacy.tax", name: "Original tax topic", relation: "split", progress: { status: "done", first_done_at: "2026-01-01", last_revised_at: null }, note: { body: "Original private note", updated_at: "2026-01-01" } }] } }));
  await page.route("**/api/v1/taxonomy/versions/*/report", route => route.fulfill({ json: report }));
  await page.route("**/api/v1/taxonomy/versions/*/sources", route => route.fulfill({ json: [{ ...source, id: source.artifact_id, paper_id: "P4", course_level: "Final", sha256: "a".repeat(64), retrieved_at: "2026-10-03", page_count: 50, edition_evidence: [source.landing_url], expected_structure: [{ kind: "unit", module: "Official Module One", chapter: "Official Chapter", name: "Official Unit", download_url: source.download_url }], heading_reconciliation: { status: "pending", expected_count: 1, accounted_count: 0, unresolved: ["Official Unit"] } }] }));
  await page.route("**/api/v1/taxonomy/versions/*/question-sources", route => route.fulfill({ json: [{ id: "model-fixture", source_family: "model", course_level: "Final", attempt_id: null, scheme_id: "2023", paper_id: "P4", paper_ids: [], group: "2", series: null, artifact_role: "question", paired_artifact_id: "model-answer-fixture", availability: "discovered", landing_url: source.landing_url, download_url: source.download_url, sha256: null, page_count: null, classification_queue: "final_metadata_review", retrieved_at: "2026-10-03" }, { id: "mock-fixture", source_family: "mock", course_level: "Foundation", attempt_id: "2026-01", scheme_id: null, paper_id: "Foundation.P1", paper_ids: [], group: null, series: "II", artifact_role: "answer", paired_artifact_id: "mock-question-fixture", availability: "missing", landing_url: source.landing_url, download_url: "", sha256: null, page_count: null, classification_queue: "outside_corpus", retrieved_at: "2026-10-03" }] }));
  await page.route("**/api/v1/taxonomy/versions/*/crosswalk", route => route.fulfill({ json: [{ id: 1, old_node_id: "legacy.tax", new_node_id: "fresh.5", relation: "split", evidence: "Textbook subdivision evidence", reviewed_by: null, reviewed_at: null }] }));
}
async function selectLeaf(page: Page, curator = false) {
  if (curator) {
    for (const name of labels.slice(1, 5)) await page.locator("summary").filter({ hasText: name }).click();
    await page.getByRole("button", { name: "subtopic Tax concept Review pending", exact: true }).click();
  } else {
    await page.getByRole("button", { name: "Expand to topics" }).click();
    await page.getByRole("treeitem", { name: /Tax concept/ }).click();
  }
}

test("index source without an audited landing page retains its PDF without an invented page link", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2"); await routes(page);
  const tree = hierarchy();
  let leaf = tree;
  while (leaf.children.length) leaf = leaf.children[0];
  leaf.sources = [{ ...source, landing_url: "", edition: "August 2024" }];
  await page.route("**/api/v1/taxonomy/versions/*/tree", route => route.fulfill({ json: [tree] }));
  await page.goto("/curator/textbooks"); await selectLeaf(page, true);
  const context = page.getByRole("region", { name: "Selected textbook concept" });
  await expect(context.getByText("August 2024 fallback", { exact: false })).toBeVisible();
  await expect(context.getByRole("link", { name: "Textbook PDF, pages 12–16" })).toHaveAttribute("href", `${source.download_url}#page=12`);
  await expect(context.getByRole("link", { name: "Official source page" })).toHaveCount(0);
});

test("recursive student explorer distinguishes fallback, applicability and preserved predecessor notes", async ({ page, request }, testInfo) => {
  await request.post("/__test/login?account_id=2"); await routes(page); await page.goto("/textbooks"); await selectLeaf(page);
  await expect(page.getByRole("navigation", { name: "Textbook breadcrumbs" })).toHaveText(labels.join(" → "));
  await expect(page.getByText("January 2026 fallback", { exact: false }).first()).toBeVisible();
  await expect(page.getByText(/May 2027 applicability: provision_review_required/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Textbook PDF, pages 12–16" }).first()).toHaveAttribute("href", `${source.download_url}#page=12`);
  await expect(page.getByRole("button", { name: "Approve reviewed descriptor revision" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Edit descriptor", exact: true })).toHaveCount(0);
  await page.getByRole("tab", { name: "History", exact: true }).click();
  await expect(page.getByText("Original private note", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Original tax topic" })).toHaveAttribute("href", "/textbooks?legacy=true&paper=P4&node=legacy.tax");
  await expect(page.getByText(/Not eligible for classification/)).toBeVisible();
  await expect(page.getByText("Heading origin: App-authored concept subdivision")).toBeVisible();
  await expect(page.getByText(/Original node: legacy.tax · Progress: done/)).toBeVisible();
  await page.screenshot({ path: `/tmp/phase3-textbook-student-${testInfo.project.name}.png`, fullPage: true });
});

test("editing an approved descriptor creates a cited unapproved revision", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2"); await routes(page);
  let current = { ...descriptor, approved: true }; let payload: unknown;
  await page.route("**/api/v1/taxonomy/nodes/*/descriptor?**", route => route.fulfill({ json: current }));
  await page.route("**/api/v1/taxonomy/nodes/*/descriptor", route => {
    payload = route.request().postDataJSON(); current = { ...current, definition: "Updated definition", revision: 2, approved: false };
    return route.fulfill({ json: { revision: 2, approved: false } });
  });
  await page.goto("/curator/textbooks"); await selectLeaf(page, true);
  await page.getByRole("tab", { name: "Descriptor", exact: true }).click();
  await expect(page.getByText("Revision 1 · Approved")).toBeVisible();
  await page.getByRole("button", { name: "Edit descriptor", exact: true }).click();
  await page.getByLabel("Concept definition", { exact: true }).fill("Updated definition");
  await page.getByRole("button", { name: "Save new descriptor revision" }).click();
  await expect(page.getByText("Revision 2 · Review pending")).toBeVisible();
  expect(payload).toEqual({ version_id: version.version_id, definition: "Updated definition", terminology: descriptor.terminology, instrument_references: descriptor.instrument_references, edition: descriptor.edition, source_ambiguities: [], inclusion: descriptor.inclusion, exclusion: descriptor.exclusion, nearby_distinctions: descriptor.nearby_distinctions, source_spans: descriptor.source_spans });
});

test("descriptor approval records displayed revision and failed approval stays pending", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2"); await routes(page);
  let payload: unknown;
  await page.route("**/api/v1/taxonomy/nodes/*/descriptor/approve", route => { payload = route.request().postDataJSON(); return route.fulfill({ status: 409, json: { detail: "Descriptor revision changed" } }); });
  await page.goto("/curator/textbooks"); await selectLeaf(page, true);
  await page.getByRole("tab", { name: "Descriptor", exact: true }).click();
  await page.getByRole("button", { name: "Approve reviewed descriptor revision" }).click();
  await expect(page.getByRole("alert")).toContainText("Descriptor revision changed");
  expect(payload).toEqual({ version_id: version.version_id, revision: 1 });
  await expect(page.getByText("Revision 1 · Review pending")).toBeVisible();
});

test("administrator release review binds approval to concrete manifest without activation", async ({ page, request }, testInfo) => {
  await request.post("/__test/login?account_id=3"); await routes(page);
  let approved: unknown; let activation = 0;
  await page.route("**/api/v1/taxonomy/versions/*/approve", route => { approved = route.request().postDataJSON(); return route.fulfill({ json: { status: "approved" } }); });
  await page.route("**/api/v1/taxonomy/versions/*/activate", route => { activation++; return route.fulfill({ status: 500 }); });
  await page.goto("/curator/taxonomy-release");
  await expect(page.getByText("Source applicability unresolved")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve this release manifest" })).toBeDisabled();
  await expect(page.getByText("2 progress records · 1 original notes")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Textbook source inventory" })).toBeVisible();
  await expect(page.getByText("P4", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Heading reconciliation: pending · 0\/1/)).toBeVisible();
  await expect(page.getByRole("cell", { name: /^Model Test Papers/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: /^Mock Test Papers/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: /^Attempt: Undated/ })).toBeVisible();
  await expect(page.getByText("Outside the Final corpus", { exact: true })).toBeVisible();
  await page.screenshot({ path: `/tmp/phase3-textbook-curator-${testInfo.project.name}.png`, fullPage: true });
  await page.unroute("**/api/v1/taxonomy/versions/*/report");
  await page.route("**/api/v1/taxonomy/versions/*/report", route => route.fulfill({ json: { ...report, activation_ready: true, blockers: [], unresolved_sources: [] } }));
  await page.reload();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Approve this release manifest" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Release approval recorded" })).toBeVisible();
  expect(approved).toEqual({ manifest_hash: version.manifest_hash }); expect(activation).toBe(0);
});

test("non-admins cannot enter release inventory and unavailable taxonomy is explicit", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2"); await page.goto("/curator/taxonomy-release");
  await expect(page.getByRole("alert")).toContainText("Administrator access required");
  await page.route("**/api/v1/taxonomy/versions", route => route.fulfill({ status: 503, json: { detail: "Textbook sources unavailable" } }));
  await page.goto("/textbooks");
  await expect(page.getByRole("alert")).toContainText("Textbook sources unavailable");
  await expect(page.getByText("No textbook taxonomy release has been drafted.")).toHaveCount(0);
});

test("legacy explorer selects preserved version explicitly and retains URL selection on reload", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2"); await routes(page);
  await page.route("**/api/v1/taxonomy/versions", route => route.fulfill({ json: [version, { ...version, version_id: "legacy-fixture", status: "legacy", taxonomy_version_id: 1 }] }));
  await page.goto("/textbooks?legacy=true");
  await expect(page.getByRole("heading", { name: "Syllabus", exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Taxonomy version" })).toHaveValue("legacy-fixture");
  await page.getByRole("combobox", { name: "Taxonomy version" }).selectOption(version.version_id);
  await expect(page).toHaveURL(/version=textbook-fixture/);
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Taxonomy version" })).toHaveValue(version.version_id);
  await page.goto("/textbooks?legacy=true");
  await expect(page.getByRole("heading", { name: "Syllabus", exact: true })).toBeVisible();
});
