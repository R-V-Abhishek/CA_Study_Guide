import { useEffect, useId, useRef, type ReactNode } from 'react';

/** Native modal semantics keep focus inside and restore the launching control. */
export function Dialog({ open, onClose, title, children, className = '' }: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    if (open) return;
    // Safari does not focus clicked buttons. Remember the actual launcher.
    const pointer = (event: PointerEvent) => {
      trigger.current = (event.target as Element).closest<HTMLElement>('button,a[href],input,select,textarea,[tabindex]');
    };
    const keyboard = () => { trigger.current = null; };
    document.addEventListener('pointerdown', pointer, true);
    document.addEventListener('keydown', keyboard, true);
    return () => { document.removeEventListener('pointerdown', pointer, true); document.removeEventListener('keydown', keyboard, true); };
  }, [open]);
  useEffect(() => {
    const dialog = ref.current!;
    if (!open) { if (dialog.open) dialog.close(); return; }
    const origin = trigger.current ?? document.activeElement as HTMLElement | null;
    if (!dialog.open) dialog.showModal();
    return () => { if (dialog.open) dialog.close(); origin?.focus(); };
  }, [open]);
  return <dialog ref={ref} className={`workspace-dialog ${className}`} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="dialog-header"><h2 id={titleId}>{title}</h2><button type="button" onClick={onClose}>Close</button></div>
    {open && children}
  </dialog>;
}
