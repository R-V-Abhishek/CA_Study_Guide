import { test, expect, browserOrigin, type APIRequestContext } from './fixtures';
import type { PublishedQuestion } from '../../packages/api-client/src/questions';

type ReaderFixture = { question_id: string; reader_part_id: string; source_id: number; paper_id: string; nodes: { id: string; name: string }[] };
async function fixture(request: APIRequestContext): Promise<ReaderFixture> { return (await request.get('/__test/fixture')).json(); }
test.beforeEach(async ({ request }) => { await request.post('/__test/reset'); await request.post('/__test/login'); });

test('published undated question reveals complete context and source, preserving filters', async ({ page, request }) => {
  const data = await fixture(request);
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/questions?q=Synthetic&answer_status=partial&source_family=practice');
  await expect(page.getByRole('link', { name: 'Synthetic reader question' })).toBeVisible();
  await page.getByRole('link', { name: 'Synthetic reader question' }).click();
  await expect(page.getByText('Synthetic shared case: a company considers two accounting requirements.')).toBeVisible();
  await expect(page.getByText('Synthetic first requirement.')).toBeVisible();
  await expect(page.getByText('Synthetic second requirement.')).toBeVisible();
  await expect(page.getByText('Undated collection', { exact: false })).toBeVisible();
  await expect(page.getByText('SYNTHETIC READER ANSWER SENTINEL')).toHaveCount(0);
  await page.getByRole('button', { name: 'Reveal answer' }).click();
  await expect(page.getByText('SYNTHETIC READER ANSWER SENTINEL')).toBeVisible();
  await expect(page.getByText('This answer is partial. Some parts have no reviewed answer.')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `test-results/phase7-reader-${test.info().project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: 'View source', exact: true }).first().click();
  await expect(page.getByRole('img', { name: 'Published question source page 1' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open PDF' })).toHaveAttribute('href', `/api/v1/published-sources/${data.source_id}`);
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('link', { name: '← Back to questions', exact: true }).click();
  await expect(page.getByLabel('Search questions')).toHaveValue('Synthetic');
  await expect(page.getByLabel('Answer availability')).toHaveValue('partial');
  await expect(page.getByLabel('Source type')).toHaveValue('practice');
  await page.reload();
  await expect(page.getByLabel('Answer availability')).toHaveValue('partial');
  expect(errors).toEqual([]);
});

test('part highlight retains sibling parts and rejects external return URLs', async ({ page, request }) => {
  const data = await fixture(request);
  await page.goto(`/questions/${data.question_id}?part=${data.reader_part_id}&return=${encodeURIComponent('//example.test/steal')}`);
  await expect(page.locator('[data-selected=true]')).toContainText('Synthetic first requirement.');
  await expect(page.getByText('Synthetic second requirement.')).toBeVisible();
  await expect(page.locator('[data-selected=true]')).toContainText('4 marks');
  await expect(page.locator('[data-selected=true]')).toContainText('Selected part');
  await expect(page.getByRole('link', { name: '← Back to questions', exact: true })).toHaveAttribute('href', '/questions');
  await expect(page.getByText('Reading does not change your syllabus progress.')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `test-results/phase7-selected-part-${test.info().project.name}.png`, fullPage: true });
  const before = await (await request.get(`/api/v1/subtopics/${data.nodes[0].id}`)).json();
  expect(before.status).toBe('not_started');
});

test('question search filters and private notes enforce account scope', async ({ page, request }) => {
  const data = await fixture(request);
  const me = await (await request.get('/api/v1/me')).json();
  await request.put(`/api/v1/subtopics/${data.nodes[0].id}/notes`, { headers: { Origin: browserOrigin(), 'X-CSRF-Token': me.csrf_token }, data: { notes: 'Synthetic private ownership sentinel' } });
  await page.goto('/questions?q=Synthetic&include_notes=true');
  await expect(page.getByText('Synthetic private ownership sentinel')).toBeVisible();
  await page.getByLabel('Answer availability').selectOption('missing');
  await expect(page.getByText('No questions match these filters')).toBeVisible();
  await page.getByLabel('Answer availability').selectOption('partial');
  await expect(page.getByRole('link', { name: 'Synthetic reader question' })).toBeVisible();
  await page.getByLabel('Search questions').fill('unfindablesynthetictoken');
  await expect(page.getByText('No matching notes.')).toBeVisible();
  await request.post('/__test/login?account_id=2');
  await page.reload();
  await page.getByLabel('Search questions').fill('Synthetic');
  await expect(page.getByText('No matching notes.')).toBeVisible();
  await expect(page.getByText('Synthetic private ownership sentinel', { exact: false })).toHaveCount(0);
});

test('explicit question demo works without API traffic', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/v1/')) requests.push(request.url()); });
  await page.goto('/questions?demo=true');
  await page.getByRole('link', { name: 'Demo complete question' }).click();
  await expect(page.getByText('A company enters into a lease. Both parts use this shared case.')).toBeVisible();
  await page.getByRole('button', { name: 'Reveal answer' }).click();
  await expect(page.getByText(/This is a synthetic demo answer/)).toBeVisible();
  expect(requests).toEqual([]);
});

test('question summary marks preserve measured zero and distinguish unavailable evidence',async ({ page,request }) => {
  const response=await (await request.get('/api/v1/questions')).json();
  const original=response.items[0];
  const marks={ whole_question_marks:0,offered_marks:0,selectable_marks:null,allocations:[],issues:[] };
  await page.route('**/api/v1/questions?*',route => route.fulfill({ json:{ ...response,total:2,items:[{ ...original,question_id:'zero-marks',display_label:'Reviewed zero marks',marks },{ ...original,question_id:'unknown-marks',display_label:'Unallocated marks',marks:null }] } }));
  await page.goto('/questions');
  await expect(page.getByRole('article').filter({ has:page.getByRole('link',{ name:'Reviewed zero marks' }) })).toContainText('Marks: 0');
  await expect(page.getByRole('article').filter({ has:page.getByRole('link',{ name:'Unallocated marks' }) })).toContainText('Marks: Not available');
});

test('topic question rows deduplicate matched parts, show their marks and return reader focus without eager reader fetches',async ({ page,request }) => {
  const data=await fixture(request);
  const published:PublishedQuestion=await (await request.get(`/api/v1/questions/${data.question_id}`)).json();
  const response=await (await request.get('/api/v1/questions')).json();
  const original=response.items.find((question:{ question_id:string }) => question.question_id === data.question_id);
  const matched=published.content.parts.map(part => ({ id:part.id,label:part.label_path ?? part.label }));
  const allocations=matched.map((part,index) => ({ part_id:part.id,marks:index === 0 ? 0 : 6,allocation_status:'reviewed' as const,choice_group:null,node_shares:[] }));
  await page.route('**/api/v1/questions?*',route => {
    if (new URL(route.request().url()).searchParams.get('subtopic_id') === data.nodes[0].id) return route.fulfill({ json:{ ...response,total:1,items:[{ ...original,matched_parts:[matched[0],matched[0],...matched.slice(1)],marks:{ ...published.marks,allocations } }] } });
    return route.continue();
  });
  let readerRequests=0;
  page.on('request',request => { if (new URL(request.url()).pathname === `/api/v1/questions/${data.question_id}`) readerRequests++; });
  await page.goto(`/syllabus?paper=${data.paper_id}&node=${data.nodes[0].id}`);
  await expect(page.getByText(`Relevant parts: ${matched.map(part => part.label).join(', ')}`,{ exact:true })).toBeVisible();
  await expect(page.getByText(`${matched[0].label}: 0 marks · ${matched[1].label}: 6 marks`,{ exact:true })).toBeVisible();
  const link=page.getByRole('link',{ name:'Read complete question',exact:true });
  expect(new URL((await link.getAttribute('href'))!,page.url()).searchParams.get('part')).toBe(matched[0].id);
  expect(readerRequests).toBe(0);
  await link.click();
  await expect(page.locator('[data-selected=true]')).toContainText('Synthetic first requirement.');
  await expect(page.getByText('Synthetic second requirement.',{ exact:true })).toBeVisible();
  await page.getByRole('link',{ name:'← Back to topic',exact:true }).click();
  await expect(page.getByRole('link',{ name:'Read complete question',exact:true })).toBeFocused();
  expect(readerRequests).toBe(1);
});

test('complete and missing answers remain explicit and changing the question hides the previous answer',async ({ page,request }) => {
  const data=await fixture(request);
  const original:PublishedQuestion=await (await request.get(`/api/v1/questions/${data.question_id}`)).json();
  const answers=original.content.parts.map((part,index) => ({ contract_version:'shared-study.v1' as const,id:`synthetic.complete-answer-${index}`,question_part_id:part.id,sequence:index,answer_text:`Synthetic complete answer for requirement ${index + 1}.`,source_spans:[],parts:[] }));
  const complete:PublishedQuestion={ ...original,question_id:'synthetic.complete',assets:[],content:{ ...original.content,question_id:'synthetic.complete',display_label:'Synthetic complete answer case',answer_status:'complete',answers,mcq:[] } };
  const missing:PublishedQuestion={ ...original,question_id:'synthetic.missing',assets:[],content:{ ...original.content,question_id:'synthetic.missing',display_label:'Synthetic missing answer case',answer_status:'missing',answers:[],mcq:[] } };
  const next:PublishedQuestion={ ...complete,question_id:'synthetic.next',content:{ ...complete.content,question_id:'synthetic.next',display_label:'Synthetic next complete case',answers:answers.map(answer => ({ ...answer,answer_text:'Synthetic next answer must stay hidden.' })) } };
  const variants=new Map([complete,missing,next].map(question => [question.question_id,question]));
  await page.route('**/api/v1/questions/synthetic.*',route => route.fulfill({ json:variants.get(new URL(route.request().url()).pathname.split('/').pop()!) }));
  await page.goto('/questions/synthetic.complete');
  await expect(page.getByRole('heading',{ name:complete.content.display_label,exact:true })).toBeVisible();
  await expect(page.getByText(answers[0].answer_text,{ exact:true })).toHaveCount(0);
  await page.getByRole('button',{ name:'Reveal answer',exact:true }).click();
  for (const answer of answers) await expect(page.getByText(answer.answer_text,{ exact:true })).toBeVisible();
  await expect(page.getByText('This answer is partial. Some parts have no reviewed answer.')).toHaveCount(0);
  // A history navigation keeps the same reader component mounted while its question ID changes.
  await page.evaluate(() => { document.body.dataset.readerDocument='retained';history.pushState(null,'','/questions/synthetic.next');window.dispatchEvent(new PopStateEvent('popstate')); });
  await expect(page.getByRole('heading',{ name:next.content.display_label,exact:true })).toBeVisible();
  expect(await page.evaluate(() => document.body.dataset.readerDocument)).toBe('retained');
  await expect(page.getByRole('button',{ name:'Reveal answer',exact:true })).toHaveAttribute('aria-expanded','false');
  await expect(page.getByText('Synthetic next answer must stay hidden.',{ exact:true })).toHaveCount(0);
  await page.evaluate(() => { history.pushState(null,'','/questions/synthetic.missing');window.dispatchEvent(new PopStateEvent('popstate')); });
  await expect(page.getByRole('heading',{ name:missing.content.display_label,exact:true })).toBeVisible();
  await expect(page.getByText('No reviewed answer is available for this question.')).toBeVisible();
  await expect(page.getByRole('button',{ name:'Reveal answer',exact:true })).toHaveCount(0);
  await expect(page.getByText('Synthetic first requirement.',{ exact:true })).toBeVisible();
  await expect(page.getByText('Synthetic second requirement.',{ exact:true })).toBeVisible();
});

for (const width of [390,1280]) test(`reader retains a long shared case, adjacent OR choices and local table scrolling at ${width}px`,async ({ page,request }) => {
  const data=await fixture(request);
  const original:PublishedQuestion=await (await request.get(`/api/v1/questions/${data.question_id}`)).json();
  const table=['| '+Array.from({ length:6 },(_,index) => `Column ${index + 1}: detailed official comparison heading`).join(' | ')+' |','| '+Array(6).fill('---').join(' | ')+' |','| '+Array.from({ length:6 },(_,index) => `Reviewed evidence and assumptions for scenario ${index + 1}`).join(' | ')+' |'].join('\n');
  const commonStem=Array.from({ length:45 },(_,index) => `Case paragraph ${index + 1}: the company evaluates the accounting requirements and the supporting source evidence.`).join('\n\n')+'\n\nEnd of the complete shared case sentinel.';
  const parts=original.content.parts.map((part,index) => ({ ...part,question_text:index === 0 ? `First alternative requirement.\n\n${table}` : 'Second alternative requirement remains visible.' }));
  const question:PublishedQuestion={ ...original,assets:[],content:{ ...original.content,common_stem:commonStem,parts,choices:parts.map(part => ({ label:part.label_path ?? part.label,role:'alternative',or_group:'A',marks:part.marks ?? null })) } };
  await page.route(`**/api/v1/questions/${data.question_id}`,route => route.fulfill({ json:question }));
  await page.setViewportSize({ width,height:900 });
  await page.goto(`/questions/${data.question_id}?part=${parts[0].id}`);
  await expect(page.getByText('End of the complete shared case sentinel.',{ exact:true })).toBeVisible();
  await expect(page.getByText('Case paragraph 1:',{ exact:false })).toBeVisible();
  for (const part of parts) await expect(page.locator(`[id="part-${part.id}"]`)).toContainText('alternative · OR group A');
  await expect(page.locator('[data-selected=true]')).toContainText('Selected part');
  await expect(page.getByText('Second alternative requirement remains visible.',{ exact:true })).toBeVisible();
  const region=page.getByRole('region',{ name:'Question table',exact:true });
  await expect(region).toBeVisible();
  expect(await region.evaluate(element => element.scrollWidth > element.clientWidth)).toBeTruthy();
  await region.evaluate(element => { element.scrollLeft=element.scrollWidth; });
  expect(await region.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});
