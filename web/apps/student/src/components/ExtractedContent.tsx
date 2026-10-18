import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { PublishedQuestion, ExtractionQuestionPart, ExtractionAnswerPart } from '@caf/api-client';
import { isDemoMode } from '../lib/demo';
import { PublishedImage } from './PublishedImage';
const marksText = (marks: number | null | undefined) => marks == null ? 'Marks not available' : `${marks} marks`;
function Content({ text }: { text: string }) { return <div className="whitespace-pre-wrap"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: ({ children }) => <div className="study-table-wrap" tabIndex={0} role="region" aria-label="Question table"><table>{children}</table></div> }}>{text}</ReactMarkdown></div>; }
function matchesChoice(part: ExtractionQuestionPart, label: string) { return label === part.label || label === part.label_path; }
function Parts({ parts, selected, choices, mcq }: { parts: ExtractionQuestionPart[]; selected: string | null; choices: PublishedQuestion['content']['choices']; mcq: PublishedQuestion['content']['mcq'] }) {
  return <div>{parts.map(part => <section id={`part-${part.id}`} key={part.id} data-selected={part.id === selected} className="reader-part"><h3>{part.label} · {marksText(part.marks)}{part.id === selected && <span className="study-meta block">Selected part</span>}</h3>{choices.filter(choice => matchesChoice(part,choice.label)).map((choice,index) => <p className="study-meta" key={index}>{choice.role}{choice.or_group && ` · OR group ${choice.or_group}`}</p>)}<Content text={part.question_text} />{mcq.filter(item => item.part_id === part.id).map(item => <fieldset key={item.part_id}><legend>Options</legend><ol className="list-[upper-alpha]">{item.options.map((option,index) => <li key={index}><Content text={option} /></li>)}</ol></fieldset>)}<Parts parts={part.parts ?? []} selected={selected} choices={choices} mcq={mcq} /></section>)}</div>;
}
function Answers({ answers, labels }: { answers: ExtractionAnswerPart[]; labels: Map<string, string> }) {
  return <div className="space-y-4">{answers.map(answer => <section key={answer.id}>{answer.question_part_id && <h3>Answer for {labels.get(answer.question_part_id) ?? 'question part'}</h3>}<Content text={answer.answer_text} /><Answers answers={answer.parts ?? []} labels={labels} /></section>)}</div>;
}

export function QuestionText({ data, selected }: { data: PublishedQuestion; selected: string | null }) {
  const parts: ExtractionQuestionPart[] = [];
  const visit = (items: ExtractionQuestionPart[]) => { for (const part of items) { parts.push(part); visit(part.parts); } };
  visit(data.content.parts);
  const labels = new Map(parts.map(part => [part.id, part.label]));
  return <section aria-label="Complete question"><h2>Complete question</h2>{data.content.common_stem && <div className="mt-6"><h3>Shared case / stem</h3><Content text={data.content.common_stem} /></div>}{data.content.question_text && <Content text={data.content.question_text} />}<Parts parts={data.content.parts ?? []} selected={selected} choices={data.content.choices} mcq={data.content.mcq} />{data.content.choices.length > 0 && <section className="reader-part"><h3>Choice structure</h3>{data.content.choices.filter(choice => !parts.some(part => matchesChoice(part,choice.label))).map((choice, index) => <p key={index}>{choice.label}: {choice.role}{choice.or_group && ` · OR group ${choice.or_group}`} · {marksText(choice.marks)}</p>)}</section>}{data.content.mcq.filter(item => !parts.some(part => part.id === item.part_id)).map(mcq => <fieldset key={mcq.part_id}><legend>{labels.get(mcq.part_id) ?? 'Question'} — options</legend><ol className="list-[upper-alpha]">{mcq.options.map((option, index) => <li key={index}><Content text={option} /></li>)}</ol></fieldset>)}{data.assets.map(asset => <figure className="space-y-2 mt-6" key={asset.id}>{isDemoMode() ? <p>Source asset preview is available for authenticated published content.</p> : <PublishedImage url={asset.url} label={`${asset.kind}, page ${asset.page}`} enlarge />}<figcaption className="study-meta">{asset.kind} · page {asset.page}{asset.concerns.length > 0 && ' · Source layout needs review'}</figcaption></figure>)}</section>;
}
export function AnswerText({ data }: { data: PublishedQuestion }) {
  const labels = new Map<string, string>();
  const visit = (items: ExtractionQuestionPart[]) => { for (const part of items) { labels.set(part.id, part.label); visit(part.parts); } };
  visit(data.content.parts);
  return <><Answers answers={data.content.answers} labels={labels} />{data.content.mcq.filter(mcq => mcq.key).map(mcq => <p key={mcq.part_id}>Key for {labels.get(mcq.part_id) ?? 'question'}: {mcq.key}</p>)}</>;
}
