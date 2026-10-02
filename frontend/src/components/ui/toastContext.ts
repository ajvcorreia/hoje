import { createContext } from 'react';

export interface ToastOptions {
  message: string;
  /** Label of the optional action button, e.g. "Undo". */
  actionLabel?: string;
  onAction?: () => void;
  /** Auto-dismiss delay; defaults to 5 s. */
  durationMs?: number;
}

export interface ToastApi {
  /** Shows a toast and returns its id. */
  show(options: ToastOptions): number;
  dismiss(id: number): void;
}

export const ToastContext = createContext<ToastApi | null>(null);
