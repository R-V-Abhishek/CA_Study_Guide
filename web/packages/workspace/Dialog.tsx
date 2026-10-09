import { useEffect, useId, useRef, type ReactNode } from 'react';

/** Native modal semantics keep focus inside and restore the launching control. */
export function Dialog({ open, onClose, title, children, className = '' }: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current!;
    if (!open) { if (dialog.open) dialog.close(); return; }
    const origin = document.activeElement as HTMLElement | null;
    if (!dialog.open) dialog.showModal();
    return () => { if (dialog.open) dialog.close(); origin?.focus(); };
  }, [open]);
  return <dialog ref={ref} className={`workspace-dialog ${className}`} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="dialog-header"><h2 id={titleId}>{title}</h2><button type="button" onClick={onClose}>Close</button></div>
    {open && children}
  </dialog>;
}
