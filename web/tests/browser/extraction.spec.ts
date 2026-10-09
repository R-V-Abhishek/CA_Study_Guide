import { test, expect, type Page } from "./fixtures";
import type { ExtractedQuestion, ExtractionDocument, ExtractionRevision } from "../../packages/api-client/src/extraction";

const span = { contract_version: "shared-study.v1" as const, document_sha256: "a".repeat(64), page_start: 1, page_end: 2, block_start: "b1", block_end: "b4" };
const question: ExtractedQuestion = {
  contract_version: "shared-study.v1",
  label_path: "Q1",
  question_id: "scope:q1", content_revision: "b".repeat(64), paper_id: "s2023.P1", source_attempt_id: null,
  display_label: "Q1", common_stem: "The company reported these balances.", question_text: "Answer both parts.",
  course_level: "Final", scheme_id: "2023", source_family: "model", source_collection_id: "Model collection 2026",
  question_status: "complete", readability_status: "concern", pairing_status: "partial", review_status: "pending",
  choices: [{ label: "Q1.a", role: "optional", or_group: "1", marks: 5 }, { label: "Q1.b", role: "optional", or_group: "1", marks: 5 }], mcq: [], assets: [], source_document_ids: [10],
  parts: [{ contract_version: "shared-study.v1", id: "q1:a", label: "(a)", label_path: "Q1.a", sequence: 0, question_text: "Compute revenue.", marks: 5, source_spans: [span], parts: [] }, { contract_version: "shared-study.v1", id: "q1:b", label: "(b)", label_path: "Q1.b", sequence: 1, question_text: "Explain treatment.", marks: 5, source_spans: [span], parts: [{ contract_version: "shared-study.v1", id: "q1:b:i", label: "(i)", label_path: "Q1.b.i", sequence: 0, question_text: "State the applicable principle.", marks: null, source_spans: [span], parts: [] }] }],
  answers: [{ contract_version: "shared-study.v1", id: "answer:a", question_part_id: "q1:a", sequence: 0, answer_text: "Revenue is 100.", source_spans: [span], parts: [] }], answer_status: "partial", source_spans: [span],
};
const document: ExtractionDocument = { id: 10, title: "Official model fixture", sha256: span.document_sha256, course_level: "Final", scheme_id: "2023", paper_id: "s2023.P1", attempt_id: null, collection_id: "Model collection 2026", doc_type_id: "model", catalog_status: "confirmed", extract_status: "processed", page_count: 2, current_revision_id: 1 };
const candidate: ExtractionRevision = { id: 2, document_id: 10, base_revision_id: 1, status: "candidate", content_digest: "b".repeat(64), profile_id: "model-question", created_at: "2026-10-04", configuration: {}, source_documents: [{ id: document.id, sha256: document.sha256, page_count: document.page_count }], quality: { questions: "passed", answers: "concern", issues: [{ code: "table", message: "Table structure requires review", severity: "concern" }] }, questions: [question] };
const previous: ExtractionRevision = { ...candidate, id: 1, status: "current", base_revision_id: null, content_digest: "c".repeat(64), questions: [{ ...question, question_text: "Previous question wording." }] };

async function routes(page: Page) {
  await page.route("**/api/v1/extraction/documents?**", route => route.fulfill({ json: { items: [document], page: 1, page_size: 20, total: 1 } }));
  await page.route("**/api/v1/extraction/documents/10/revisions?**", route => route.fulfill({ json: { items: [candidate, previous], page: 1, page_size: 20, total: 2 } }));
  await page.route("**/api/v1/extraction/revisions/2", route => route.fulfill({ json: candidate }));
  await page.route("**/api/v1/extraction/revisions/1", route => route.fulfill({ json: previous }));
  await page.route("**/api/v1/extraction/revisions/2/questions?**", route => route.fulfill({ json: { items: [question], page: 1, page_size: 10, total: 1 } }));
  for (const url of ["**/api/v1/extraction/documents/10/pairs?**", "**/api/v1/extraction/revisions/*/blocks?**", "**/api/v1/extraction/revisions/*/assets?**", "**/api/v1/extraction/revisions/*/reviews?**", "**/api/v1/extraction/revisions/*/reconciliation?**"]) await page.route(url, route => route.fulfill({ json: { items: [], page: 1, page_size: 10, total: 0 } }));
  await page.route("**/api/v1/extraction/documents/10/pages/*", route => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><rect width="400" height="500" fill="white"/><text x="20" y="30">Original fixture page</text></svg>' }));
}

test("active student reviews complete extracted trees and source fidelity separately from classification", async ({ page, request }, testInfo) => {
  await request.post("/__test/login?account_id=2"); await routes(page);
  let review: unknown;
  await page.route("**/api/v1/extraction/revisions/2/reviews", route => { review = route.request().postDataJSON(); return route.fulfill({ json: { id: 7 } }); });
  await page.goto("/curator/extraction");
  await expect(page.getByRole("link", { name: "Extraction", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await expect(page.getByText("The company reported these balances.", { exact: true })).toHaveCount(1);
  await expect(page.getByText("Compute revenue.", { exact: true })).toBeVisible();
  await expect(page.getByText("State the applicable principle.", { exact: true })).toBeVisible();
  await expect(page.getByText("Revenue is 100.", { exact: true })).toBeVisible();
  await expect(page.getByText("Available answers · partial", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Original document 10, page 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Promote candidate revision" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Quality checks" }).click();
  await expect(page.getByLabel("Quality dimension").locator("option[value=metadata]")).toHaveCount(0);
  await expect(page.getByLabel("Quality dimension").locator("option[value=pairing]")).toHaveCount(1);
  await page.getByLabel("Quality dimension").selectOption("readability");
  await page.getByLabel("Review result").selectOption("concern");
  await page.getByLabel("Review note").fill("The second-page table needs source comparison.");
  await page.getByRole("button", { name: "Record extraction quality review" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Extraction quality review recorded" })).toBeVisible();
  expect(review).toEqual({ dimension: "readability", status: "concern", note: "The second-page table needs source comparison." });
  await page.screenshot({ path: `/tmp/phase4-extraction-review-${testInfo.project.name}.png`, fullPage: true });
});

test("administrator compares immutable revisions and promotion retains stale revision failures", async ({ page, request }) => {
  await request.post("/__test/login?account_id=3"); await routes(page);
  let promotion: unknown;
  await page.route("**/api/v1/extraction/revisions/2/promote", route => { promotion = route.request().postDataJSON(); return route.fulfill({ status: 409, json: { detail: "Current revision changed" } }); });
  await page.goto("/curator/extraction"); await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await page.getByLabel("Compare revision").selectOption("1");
  await page.getByRole("tab", { name: "Revision differences" }).click();
  await expect(page.getByText("Previous question wording.", { exact: true })).toBeVisible();
  await expect(page.getByText("Content differs. Compare question and answer trees before promotion.")).toBeVisible();
  await page.getByRole("tab", { name: "Quality checks" }).click();
  await page.getByRole("button", { name: "Promote candidate revision" }).click();
  await expect(page.getByRole("button", { name: "Confirm promotion" })).toBeDisabled();
  await page.getByLabel("I compared the complete candidate, original sources, quality reviews and revision differences.").check();
  await page.getByRole("button", { name: "Confirm promotion" }).click();
  await expect(page.getByRole("alert")).toContainText("Current revision changed");
  expect(promotion).toEqual({ expected_current_revision_id: 1 });
  await expect(page.getByText("Candidate promoted. Previous extraction history remains available.")).toHaveCount(0);
});

test("source page errors remain explicit and unavailable extraction is never an empty success", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2"); await routes(page);
  await page.route("**/api/v1/extraction/documents/10/pages/*", route => route.fulfill({ status: 503, json: { detail: "Rendering unavailable" } }));
  await page.goto("/curator/extraction"); await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await expect(page.getByRole("alert")).toContainText("Source page unavailable (503)");
  await expect(page.getByRole("button", { name: "Previous page", exact: true })).toBeDisabled();
  await page.getByLabel("Page", { exact: true }).fill("2");
  await expect(page.getByRole("button", { name: "Next page", exact: true })).toBeDisabled();
  await page.route("**/api/v1/extraction/documents?**", route => route.fulfill({ status: 503, json: { detail: "Extraction database unavailable" } }));
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Extraction database unavailable");
  await expect(page.getByText("No acquired source documents are available.")).toHaveCount(0);
});

test("answer spans select the actual answer document and bounded original page", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2"); await routes(page);
  const answerSpan = { ...span, document_sha256: "d".repeat(64), page_start: 3, page_end: 3 };
  const paired = { ...question, answers: [{ ...question.answers[0], source_spans: [answerSpan] }] };
  await page.route("**/api/v1/extraction/revisions/2", route => route.fulfill({ json: { ...candidate, questions: [paired], source_documents: [...candidate.source_documents, { id: 11, sha256: answerSpan.document_sha256, page_count: 3 }] } }));
  await page.route("**/api/v1/extraction/revisions/2/questions?**", route => route.fulfill({ json: { items: [paired], total: 1, page: 1, page_size: 10 } }));
  await page.route("**/api/v1/extraction/documents/11/pages/3", route => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text y="20">Answer source</text></svg>' }));
  await page.goto("/curator/extraction"); await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await page.getByRole("button", { name: "Source pages 3–3", exact: true }).click();
  await expect(page.getByRole("img", { name: "Original document 11, page 3" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next page", exact: true })).toBeDisabled();
});

test("ambiguous answers retain competing literal text and their actual source pages", async ({ page, request }) => {
  await request.post("/__test/login?account_id=2"); await routes(page);
  const ambiguous: ExtractedQuestion = { ...question, pairing_status: "ambiguous", answers: [], pairing_candidates: [{
    part_id: "q1:a", label_path: "Q1.a", status: "ambiguous", candidates: [
      { answer_doc_id: 11, label_path: "Q1.a", answer_text: "First official candidate answer.", page_start: 2, page_end: 2, block_start: "a1", block_end: "a2", mcq_correct_option: null },
      { answer_doc_id: 11, label_path: "Q1.a.repeat2", answer_text: "Conflicting official candidate answer.", page_start: 3, page_end: 3, block_start: "a3", block_end: "a4", mcq_correct_option: null },
    ],
  }] };
  await page.route("**/api/v1/extraction/revisions/2", route => route.fulfill({ json: { ...candidate, questions: [ambiguous], source_documents: [...candidate.source_documents, { id: 11, sha256: "d".repeat(64), page_count: 3 }] } }));
  await page.route("**/api/v1/extraction/revisions/2/questions?**", route => route.fulfill({ json: { items: [ambiguous], total: 1, page: 1, page_size: 10 } }));
  await page.route("**/api/v1/extraction/documents/11/pages/3", route => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text y="20">Conflicting source</text></svg>' }));
  await page.goto("/curator/extraction"); await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await expect(page.getByText("2 candidate answers require source review.", { exact: true })).toBeVisible();
  await expect(page.getByText("First official candidate answer.", { exact: true })).toBeVisible();
  await expect(page.getByText("Conflicting official candidate answer.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Candidate source pages 3–3 · document 11", exact: true }).click();
  await expect(page.getByRole("img", { name: "Original document 11, page 3" })).toBeVisible();
});

test("admin corrections create a candidate and preserve scoped source-span evidence", async ({ page, request }) => {
  await request.post("/__test/login?account_id=3"); await routes(page);
  let corrected: unknown;
  await page.route("**/api/v1/extraction/revisions/2/corrections", route => { corrected = route.request().postDataJSON(); return route.fulfill({ status: 422, json: { detail: "Correction source block outside selected span" } }); });
  await page.goto("/curator/extraction"); await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await page.getByLabel("Scoped question or part").selectOption("Q1.b.i");
  await page.getByLabel("Correction field").selectOption("source_span");
  await page.getByLabel("First source page").fill("1"); await page.getByLabel("Last source page").fill("2");
  await page.getByLabel("First block key").fill("b1"); await page.getByLabel("Last block key").fill("b4");
  await page.getByLabel("Correction reason").fill("Compared the continuation with the original pages.");
  await page.getByRole("button", { name: "Create corrected candidate revision" }).click();
  expect(corrected).toEqual({ label_path: "Q1.b.i", reason: "Compared the continuation with the original pages.", page_start: 1, page_end: 2, block_start: "b1", block_end: "b4" });
  await expect(page.getByRole("alert")).toContainText("Correction source block outside selected span");
  await expect(page.getByLabel("Extraction revision")).toHaveValue("2");
});

test("administrator resolves an ambiguous answer using its recorded source candidate", async ({ page, request }) => {
  await request.post("/__test/login?account_id=3"); await routes(page);
  const ambiguous: ExtractedQuestion = { ...question, pairing_status: "ambiguous", answers: [], pairing_candidates: [{
    part_id: "q1:a", label_path: "Q1.a", status: "ambiguous", candidates: [
      { answer_doc_id: 11, label_path: "Q1.a", answer_text: "First source answer.", page_start: 2, page_end: 2, block_start: "a1", block_end: "a2", mcq_correct_option: null },
      { answer_doc_id: 11, label_path: "Q1.a.repeat2", answer_text: "Second source answer.", page_start: 3, page_end: 3, block_start: "a3", block_end: "a4", mcq_correct_option: null },
    ],
  }] };
  await page.route("**/api/v1/extraction/revisions/2", route => route.fulfill({ json: { ...candidate, questions: [ambiguous], source_documents: [...candidate.source_documents, { id: 11, sha256: "d".repeat(64), page_count: 3 }] } }));
  await page.route("**/api/v1/extraction/revisions/2/questions?**", route => route.fulfill({ json: { items: [ambiguous], total: 1, page: 1, page_size: 10 } }));
  let correction: unknown;
  await page.route("**/api/v1/extraction/revisions/2/corrections", route => {
    correction = route.request().postDataJSON();
    return route.fulfill({ status: 409, json: { detail: "Correction source is stale; select the current revision" } });
  });
  await page.goto("/curator/extraction"); await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await page.getByLabel("Scoped question or part").selectOption("Q1.a");
  await page.getByLabel("Correction field").selectOption("answer_candidate");
  await expect(page.getByLabel("Corrected value")).toHaveCount(0);
  await page.getByLabel("Selected answer source", { exact: true }).selectOption("Q1.a.repeat2");
  await page.getByLabel("Correction reason").fill("Selected the second recorded answer after comparing the original source pages.");
  await page.getByRole("button", { name: "Create corrected candidate revision" }).click();
  expect(correction).toEqual({ label_path: "Q1.a", answer_candidate_label: "Q1.a.repeat2", reason: "Selected the second recorded answer after comparing the original source pages." });
  await expect(page.getByRole("alert")).toContainText("Correction source is stale");
  await expect(page.getByLabel("Extraction revision")).toHaveValue("2");
});

test("administrator pairs documents with evidence and inspects protected source crops", async ({ page, request }) => {
  await request.post("/__test/login?account_id=3"); await routes(page);
  let payload: unknown;
  let items: { id: number; question_document_id: number; answer_document_id: number; status: string; evidence: { administrator_note: string } }[] = [];
  await page.route("**/api/v1/extraction/documents/10/pairs?**", route => route.fulfill({ json: { items, total: items.length, page: 1, page_size: 10 } }));
  await page.route("**/api/v1/extraction/documents/10/pairs", route => {
    payload = route.request().postDataJSON(); items = [{ id: 8, question_document_id: 10, answer_document_id: 11, status: "confirmed", evidence: { administrator_note: "Official navigation confirms the same model collection and paper." } }];
    return route.fulfill({ json: items[0] });
  });
  await page.route("**/api/v1/extraction/revisions/2/assets?**", route => route.fulfill({ json: { items: [{ id: 5, page: 2, kind: "table", bbox: [0, 0, 100, 100], concerns: ["Calculation columns require comparison"] }], total: 1, page: 1, page_size: 10 } }));
  await page.route("**/api/v1/extraction/assets/5/image", route => {
    expect(route.request().headers()["x-expected-account-id"]).toBe("3");
    return route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text y="20">Source table</text></svg>' });
  });
  await page.goto("/curator/extraction"); await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await page.getByLabel("Answer document ID").fill("11"); await page.getByLabel("Pairing evidence").fill("Official navigation confirms the same model collection and paper.");
  await page.getByRole("button", { name: "Confirm document pair", exact: true }).click();
  await expect(page.getByText("Question document 10 → answer document 11 · confirmed")).toBeVisible();
  expect(payload).toEqual({ answer_document_id: 11, evidence: "Official navigation confirms the same model collection and paper." });
  await page.getByRole("button", { name: "View table on page 2", exact: true }).click();
  await expect(page.getByRole("img", { name: "Original source asset 5" })).toBeVisible();
});

test("administrator reviews original pages and confirms ranges before any extraction exists", async ({ page, request }) => {
  await request.post("/__test/login?account_id=3"); await routes(page);
  const pending = { ...document, scheme_id: "s2023", catalog_status: "needs_curation", paper_id: "s2023.P2", doc_type_id: "model_question", metadata_evidence: { conflicts: [{ field: "paper_id", navigation: "s2023.P2", content: "s2023.P1" }] } };
  await page.route("**/api/v1/extraction/documents?**", route => route.fulfill({ json: { items: [pending], total: 1, page: 1, page_size: 20 } }));
  await page.route("**/api/v1/extraction/documents/10/revisions?**", route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } }));
  let confirmed: unknown;
  await page.route("**/api/v1/curate/documents/10/confirm", route => { confirmed = route.request().postDataJSON(); return route.fulfill({ json: { id: 10, catalog_status: "confirmed" } }); });
  await page.goto("/curator/extraction"); await page.getByRole("button", { name: /^Official model fixture/ }).click();
  await expect(page.getByRole("img", { name: "Original document 10, page 1" })).toBeVisible();
  await expect(page.getByText("No extraction revision has been generated for this document.")).toBeVisible();
  await expect(page.getByText("paper_id: navigation s2023.P2; document s2023.P1", { exact: true })).toBeVisible();
  await page.getByLabel("Source paper", { exact: true }).selectOption("s2023.P1");
  await page.getByLabel("Source collection", { exact: true }).fill("Reviewed official model collection");
  await page.getByRole("button", { name: "Add paper range", exact: true }).click();
  await page.getByLabel("Range 1 last page", { exact: true }).fill("2");
  await page.getByRole("button", { name: "Confirm source metadata", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Source metadata confirmed." })).toBeVisible();
  expect(confirmed).toEqual({ course_level: "final", scheme_id: "s2023", paper_id: "s2023.P1", attempt_id: null, collection_id: "Reviewed official model collection", doc_type_id: "model_question", paper_page_ranges: [{ paper_id: "s2023.P1", page_start: 1, page_end: 2 }] });
});
