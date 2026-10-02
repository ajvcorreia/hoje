import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ToastContext, type ToastApi, type ToastOptions } from './toastContext';

interface ToastItem extends ToastOptions {
  id: number;
}

const DEFAULT_DURATION_MS = 5000;

function ToastView({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: number) => void }) {
  const { id, durationMs = DEFAULT_DURATION_MS } = toast;
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(id), durationMs);
    return () => window.clearTimeout(timer);
  }, [id, durationMs, onDismiss]);
  return (
    <div className="pointer-events-auto flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2 text-sm shadow-sm">
      <span>{toast.message}</span>
      {toast.actionLabel ? (
        <button
          type="button"
          className="min-h-9 rounded-md px-2 font-medium text-accent hover:bg-surface-muted"
          onClick={() => {
            toast.onAction?.();
            onDismiss(id);
          }}
        >
          {toast.actionLabel}
        </button>
      ) : null}
    </div>
  );
}

/** Provides `useToast()` and renders the live region that holds the toasts. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((t) => t.id !== id));
  }, []);
  const show = useCallback((options: ToastOptions) => {
    const id = nextId.current;
    nextId.current += 1;
    setItems((current) => [...current.slice(-2), { ...options, id }]);
    return id;
  }, []);
  const api = useMemo<ToastApi>(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 max-md:bottom-20"
      >
        {items.map((t) => (
          <ToastView key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
