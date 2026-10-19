import type { ClassificationCandidate, ClassificationQueueItem, PartMapping } from "@caf/api-client";
import type { ExtractionQuestionPart, ExtractionAnswerPart } from "@caf/api-client/src/extraction";

export type Candidate = ClassificationCandidate;

export function QuestionParts({ parts, selected, onSelect }: { parts: ExtractionQuestionPart[]; selected?: string | null; onSelect?: (id: string) => void }) {
  return <>{parts.map(part => <section key={part.id} id={`part-${part.id}`} className={`py-4 border-t border-slate-600 ${selected === part.id ? "border-l-4 border-indigo-400 pl-3" : ""}`}><p>{onSelect ? <button type="button" className="underline min-h-10" onClick={() => onSelect(part.id)}>{part.label_path ?? part.label}</button> : part.label_path ?? part.label}{part.marks !== null && part.marks !== undefined ? ` · ${part.marks} marks` : ""}{selected === part.id && " · Selected part"}</p><p className="whitespace-pre-wrap">{part.question_text}</p><QuestionParts parts={part.parts} selected={selected} onSelect={onSelect} /></section>)}</>;
}

export function Answers({ parts }: { parts: ExtractionAnswerPart[] }) {
  return <>{parts.map(part => <section key={part.id} className="py-4 border-t border-slate-600"><p className="text-sm">{part.question_part_id?.split(":").slice(1).join(":") || "Whole question"}</p><p className="whitespace-pre-wrap">{part.answer_text}</p><Answers parts={part.parts} /></section>)}</>;
}

export function LabelPath({ id, item }: { id: string; item: ClassificationQueueItem }) {
  const candidate = (item.candidates as Candidate[]).find(value => value.node_id === id);
  return <span>{candidate?.path.map(node => node.name).join(" → ") ?? id}</span>;
}

export function MappingSummary({ mapping, item }: { mapping?: PartMapping; item: ClassificationQueueItem }) {
  if (!mapping) return <span>No previous mapping</span>;
  return <span>{mapping.excluded ? "Excluded" : mapping.outcome}{mapping.primary_node_id && <> · Primary: <LabelPath id={mapping.primary_node_id} item={item} /></>}{(mapping.secondary_node_ids ?? []).map(id => <span key={id}> · Secondary: <LabelPath id={id} item={item} /></span>)}</span>;
}

export function MappingEvidence({ mapping }: { mapping: PartMapping }) {
  // These fields are produced by caf_l3.textbook; provenance stays in its disclosure.
  const evidence = mapping.evidence as { core_tested_concept?: string; label_evidence?: Record<string, string>; matched_terms?: Record<string, string[]> };
  return <div><h4 className="font-semibold">Why these labels were suggested</h4>{evidence.core_tested_concept && <p>{evidence.core_tested_concept}</p>}{Object.entries(evidence.label_evidence ?? {}).map(([id, reason]) => <p key={id}>{reason}</p>)}{Object.entries(evidence.matched_terms ?? {}).map(([id, terms]) => <p key={id}>Matched terminology: {terms.join(", ")}</p>)}{!evidence.core_tested_concept && !evidence.label_evidence && !evidence.matched_terms && <p>No plain-language model evidence was recorded. Compare the complete question with the descriptor and official source.</p>}</div>;
}
