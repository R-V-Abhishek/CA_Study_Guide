import type { ClassificationQueueItem, PartMapping } from "@caf/api-client";
import type { ExtractionQuestionPart, ExtractionAnswerPart } from "@caf/api-client/src/extraction";

export type Candidate = { node_id: string; path: { id: string; name: string; level: string }[]; descriptor_revision_id: number; descriptor: Record<string, unknown>; textbook_references: unknown[] };

export function QuestionParts({ parts }: { parts: ExtractionQuestionPart[] }) {
  return <>{parts.map(part => <div key={part.id} className="border-l border-slate-600 pl-3"><p>{part.label_path ?? part.label}{part.marks !== null && part.marks !== undefined ? ` · ${part.marks} marks` : ""}</p><p className="whitespace-pre-wrap text-sm">{part.question_text}</p><QuestionParts parts={part.parts} /></div>)}</>;
}

export function Answers({ parts }: { parts: ExtractionAnswerPart[] }) {
  return <>{parts.map(part => <div key={part.id} className="border-l border-slate-600 pl-3"><p className="text-xs">{part.question_part_id?.split(":").slice(1).join(":") || "Whole question"}</p><p className="whitespace-pre-wrap text-sm">{part.answer_text}</p><Answers parts={part.parts} /></div>)}</>;
}

export function LabelPath({ id, item }: { id: string; item: ClassificationQueueItem }) {
  const candidate = (item.candidates as Candidate[]).find(value => value.node_id === id);
  return <span>{candidate?.path.map(node => node.name).join(" → ") ?? id}</span>;
}

export function MappingSummary({ mapping, item }: { mapping?: PartMapping; item: ClassificationQueueItem }) {
  if (!mapping) return <span>No previous mapping</span>;
  return <span>{mapping.excluded ? "Excluded" : mapping.outcome}{mapping.primary_node_id && <> · Primary: <LabelPath id={mapping.primary_node_id} item={item} /></>}{(mapping.secondary_node_ids ?? []).map(id => <span key={id}> · Secondary: <LabelPath id={id} item={item} /></span>)}</span>;
}
