import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface PopoverProps {
  /** Element the popover is anchored to (e.g. a day cell). */
  anchor: HTMLElement;
  /** Accessible name of the popover. */
  label: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

const GAP = 6;
const MARGIN = 8;

/**
 * Non-modal popover anchored to an element. On open it focuses `[data-autofocus]` (or the
 * first focusable child); Esc and clicks outside close it, and focus returns to the anchor.
 * It flips/clamps to stay inside the viewport.
 */
export function Popover({ anchor, label, onClose, children, className }: PopoverProps) {
  const labelId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  const place = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const a = anchor.getBoundingClientRect();
    const w = panel.offsetWidth;
    const h = panel.offsetHeight;
    let left = a.right + GAP;
    if (left + w > window.innerWidth - MARGIN) left = a.left - GAP - w;
    left = Math.min(Math.max(MARGIN, left), Math.max(MARGIN, window.innerWidth - w - MARGIN));
    let top = a.top;
    if (top + h > window.innerHeight - MARGIN) top = window.innerHeight - h - MARGIN;
    top = Math.max(MARGIN, top);
    setPos({ top, left });
  }, [anchor]);

  useLayoutEffect(() => {
    place();
  }, [place]);

  // Focus only once the panel is positioned: while `pos` is null it is `visibility: hidden`,
  // and browsers silently refuse to focus elements inside a hidden subtree.
  const focusedRef = useRef(false);
  useEffect(() => {
    if (!pos || focusedRef.current) return;
    focusedRef.current = true;
    const panel = panelRef.current;
    (
      panel?.querySelector<HTMLElement>('[data-autofocus]') ??
      panel?.querySelector<HTMLElement>(FOCUSABLE) ??
      panel
    )?.focus();
  }, [pos]);

  useEffect(() => {
    const panel = panelRef.current;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current();
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && !panel?.contains(target) && !anchor.contains(target)) onCloseRef.current();
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('resize', place);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('resize', place);
      // Return focus to the anchor unless focus already moved somewhere else on purpose.
      const active = document.activeElement;
      if (!active || active === document.body || panel?.contains(active)) {
        if (anchor.isConnected) anchor.focus();
      }
    };
  }, [anchor, place]);

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-labelledby={labelId}
      tabIndex={-1}
      className={`fixed z-40 w-72 max-w-[calc(100vw-1rem)] rounded-lg border border-border bg-surface p-3 shadow-md outline-none ${className ?? ''}`}
      style={{ top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? 'visible' : 'hidden' }}
    >
      <span id={labelId} className="sr-only">
        {label}
      </span>
      {children}
    </div>,
    document.body,
  );
}
