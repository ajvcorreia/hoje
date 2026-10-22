import { useSyncExternalStore } from 'react';

export const MIN_PILLS_WIDTH = 7;
export const MAX_PILLS_WIDTH = 20;
export const DEFAULT_PILLS_WIDTH = 10;

export const PILLS_WIDTH_KEY = 'hoje.pillsWidth';

/** Whole rem, clamped to the allowed range; anything that is not a number gives the default. */
export function clampPillsWidth(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  if (value === null || value === '' || !Number.isFinite(n)) return DEFAULT_PILLS_WIDTH;
  return Math.min(MAX_PILLS_WIDTH, Math.max(MIN_PILLS_WIDTH, Math.round(n)));
}

/** Used when localStorage is unavailable, so the choice still applies for this session. */
let fallback = DEFAULT_PILLS_WIDTH;
const listeners = new Set<() => void>();

export function readPillsWidth(): number {
  try {
    return clampPillsWidth(window.localStorage.getItem(PILLS_WIDTH_KEY));
  } catch {
    return fallback;
  }
}

export function storePillsWidth(width: number): void {
  fallback = clampPillsWidth(width);
  try {
    window.localStorage.setItem(PILLS_WIDTH_KEY, String(fallback));
  } catch {
    // Storage may be unavailable; the in-memory fallback keeps the choice for this session.
  }
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === PILLS_WIDTH_KEY) notify();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(notify);
    window.removeEventListener('storage', onStorage);
  };
}

/** Width in rem of the category pills column when it is on the left or right (per device). */
export function usePillsWidth(): [number, (width: number) => void] {
  const width = useSyncExternalStore(subscribe, readPillsWidth, () => DEFAULT_PILLS_WIDTH);
  return [width, storePillsWidth];
}
