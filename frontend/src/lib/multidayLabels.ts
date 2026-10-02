import { useSyncExternalStore } from 'react';

export const MULTIDAY_LABEL_MODES = ['horizontal', 'vertical'] as const;
export type MultidayLabelMode = (typeof MULTIDAY_LABEL_MODES)[number];

export const MULTIDAY_LABELS_KEY = 'hoje.multidayLabels';

export function isMultidayLabelMode(value: unknown): value is MultidayLabelMode {
  return typeof value === 'string' && (MULTIDAY_LABEL_MODES as readonly string[]).includes(value);
}

/** Used when localStorage is unavailable, so the choice still applies for this session. */
let fallback: MultidayLabelMode = 'horizontal';
const listeners = new Set<() => void>();

export function readMultidayLabelMode(): MultidayLabelMode {
  try {
    const value = window.localStorage.getItem(MULTIDAY_LABELS_KEY);
    return isMultidayLabelMode(value) ? value : 'horizontal';
  } catch {
    return fallback;
  }
}

export function storeMultidayLabelMode(mode: MultidayLabelMode): void {
  fallback = mode;
  try {
    window.localStorage.setItem(MULTIDAY_LABELS_KEY, mode);
  } catch {
    // Storage may be unavailable; the in-memory fallback keeps the choice for this session.
  }
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === MULTIDAY_LABELS_KEY) notify();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(notify);
    window.removeEventListener('storage', onStorage);
  };
}

/** Current mode plus a setter; every consumer re-renders on change (this tab and others). */
export function useMultidayLabelMode(): [MultidayLabelMode, (mode: MultidayLabelMode) => void] {
  const serverMode = (): MultidayLabelMode => 'horizontal';
  const mode = useSyncExternalStore(subscribe, readMultidayLabelMode, serverMode);
  return [mode, storeMultidayLabelMode];
}
