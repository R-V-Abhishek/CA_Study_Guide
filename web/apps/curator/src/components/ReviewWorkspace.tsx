import { useEffect, useRef, useState, type ReactNode } from "react";
import "./review-workspace.css";

export type ReviewTab = "Queue" | "Question" | "Answer" | "Labels" | "Evidence";

/** Responsive evidence workspace. Presentation changes never unmount unsaved forms. */
export function ReviewWorkspace({ queue, question, answer, labels, evidence, footer, tab, changeTab }: {
  queue: ReactNode; question: ReactNode; answer: ReactNode; labels: ReactNode;
  evidence: ReactNode; footer: ReactNode; tab: ReviewTab; changeTab: (tab: ReviewTab) => void;
}) {
  const [queueWidth, setQueueWidth] = useState(260);
  const [labelWidth, setLabelWidth] = useState(360);
  const [queueOpen, setQueueOpen] = useState(false);
  const queueButton = useRef<HTMLButtonElement>(null);
  const queueDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (queueOpen) queueDialog.current?.showModal();
    else if (queueDialog.current?.open) queueDialog.current.close();
  }, [queueOpen]);
  const resize = (side: "queue" | "labels", difference: number) => {
    if (side === "queue") setQueueWidth(value => Math.min(340, Math.max(200, value + difference)));
    else setLabelWidth(value => Math.min(440, Math.max(300, value + difference)));
  };
  const separator = (side: "queue" | "labels") => <div role="separator" tabIndex={0} aria-label={`Resize ${side} pane`} aria-orientation="vertical" aria-valuemin={side === "queue" ? 200 : 300} aria-valuemax={side === "queue" ? 340 : 440} aria-valuenow={side === "queue" ? queueWidth : labelWidth} className={`review-separator review-${side}-separator`}
    onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); resize(side, (event.key === "ArrowRight" ? 20 : -20) * (side === "queue" ? 1 : -1)); } }}
    onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); }}
    onPointerMove={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) resize(side, event.movementX * (side === "queue" ? 1 : -1)); }}
    onPointerUp={event => event.currentTarget.releasePointerCapture(event.pointerId)} />;
  const panes = (Object.keys({ Queue: queue, Question: question, Answer: answer, Labels: labels, Evidence: evidence }) as ReviewTab[]);
  return <>
    <button ref={queueButton} type="button" className="review-queue-toggle" onClick={() => setQueueOpen(true)}>Open review queue</button>
    <div role="tablist" aria-label="Review workspace" className="review-tabs">{panes.map(name => <button key={name} role="tab" aria-selected={tab === name} aria-controls={`review-${name}`} id={`tab-${name}`} tabIndex={tab === name ? 0 : -1} onClick={() => changeTab(name)} onKeyDown={event => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const next = panes[(panes.indexOf(name) + (event.key === "ArrowRight" ? 1 : 4)) % 5]; changeTab(next); document.getElementById(`tab-${next}`)?.focus(); } }}>{name}</button>)}</div>
    <div className="review-workspace" style={{ "--queue-width": `${queueWidth}px`, "--label-width": `${labelWidth}px` } as React.CSSProperties} data-active-tab={tab}>
      <aside id="review-Queue" className="review-pane review-queue" aria-label="Question review queue">{queue}</aside>{separator("queue")}
      <div className="review-reading"><section id="review-Question" tabIndex={-1} className="review-question review-pane" aria-label="Complete question">{question}</section><section id="review-Answer" tabIndex={-1} className="review-answer review-pane" aria-label="Complete answer">{answer}</section></div>
      {separator("labels")}<aside className="review-labels-column"><section id="review-Labels" tabIndex={-1} className="review-labels review-pane" aria-label="Part labels">{labels}</section><section id="review-Evidence" tabIndex={-1} className="review-evidence review-pane" aria-label="Review evidence">{evidence}</section></aside>
    </div><div className="review-final-bar">{footer}</div>
    <dialog ref={queueDialog} className="review-queue-dialog" onCancel={() => setQueueOpen(false)} onClose={() => { setQueueOpen(false); queueButton.current?.focus(); }}><button type="button" onClick={() => setQueueOpen(false)}>Close queue</button>{queueOpen && queue}</dialog>
  </>;
}
