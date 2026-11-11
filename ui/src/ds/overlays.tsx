// Dialogs and toasts. A decision that needs a reason is asked for in a proper dialog with a
// labelled field — never a browser prompt.

import { CheckCircle2, CircleAlert, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Button, cx, Field, Textarea } from "./primitives";

export function Dialog({
  open, onClose, title, description, children, footer, wide,
}: { open: boolean; onClose: () => void; title: string; description?: ReactNode; children?: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-950/45 p-4 pt-[12vh] animate-fade" onMouseDown={onClose}>
      <div
        ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} onMouseDown={(e) => e.stopPropagation()}
        className={cx("w-full rounded-lg border border-line bg-white shadow-pop outline-none animate-rise", wide ? "max-w-2xl" : "max-w-md")}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-ink-900">{title}</h2>
            {description && <p className="mt-1 text-[13px] text-ink-500">{description}</p>}
          </div>
          <button onClick={onClose} className="rounded p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-800" aria-label="Close"><X size={16} /></button>
        </div>
        {children && <div className="px-5 py-4">{children}</div>}
        {footer && <div className="flex justify-end gap-2 border-t border-line bg-ink-50/50 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

/** Confirm an action, optionally with a reason the action records. */
export function ConfirmDialog({
  open, onClose, onConfirm, title, description, confirmLabel, danger, reason, busy,
}: {
  open: boolean; onClose: () => void; onConfirm: (reason: string) => void; title: string; description?: ReactNode;
  confirmLabel: string; danger?: boolean; reason?: { label: string; required?: boolean; placeholder?: string }; busy?: boolean;
}) {
  const [text, setText] = useState("");
  useEffect(() => { if (open) setText(""); }, [open]);
  const blocked = Boolean(reason?.required) && !text.trim();
  return (
    <Dialog
      open={open} onClose={onClose} title={title} description={description}
      footer={<>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant={danger ? "danger" : "primary"} loading={busy} disabled={blocked} onClick={() => onConfirm(text.trim())}>{confirmLabel}</Button>
      </>}
    >
      {reason && (
        <Field label={reason.label} required={reason.required}>
          <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={reason.placeholder} autoFocus />
        </Field>
      )}
    </Dialog>
  );
}

// ── Toasts ───────────────────────────────────────────────────────────────────
interface Toast { id: number; tone: "ok" | "bad"; message: string }
const ToastContext = createContext<(tone: Toast["tone"], message: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], message: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, message }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "bad" ? 7000 : 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={cx("pointer-events-auto flex items-start gap-2.5 rounded-md border bg-white px-3.5 py-3 text-sm shadow-pop animate-rise", t.tone === "ok" ? "border-ok-line" : "border-bad-line")}>
            {t.tone === "ok" ? <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-ok-fg" /> : <CircleAlert size={17} className="mt-0.5 shrink-0 text-bad-fg" />}
            <span className="text-ink-800">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const push = useContext(ToastContext);
  return { success: (m: string) => push("ok", m), error: (m: string) => push("bad", m) };
}
