import { useSyncExternalStore } from 'react';

export const MAX_EVENTS_KEY = 'hoje.maxEventsPerDay';
export const MIN_MAX_EVENTS = 1;
export const MAX_MAX_EVENTS = 6;
/** Two side-by-side halves, as the month grid always drew them. */
export const DEFAULT_MAX_EVENTS = 2;

/** Clamps to the allowed range; anything that is not a number gives the default. */
export function clampMaxEvents(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return DEFAULT_MAX_EVENTS;
  return Math.min(MAX_MAX_EVENTS, Math.max(MIN_MAX_EVENTS, Math.round(n)));
}

/** Used when localStorage is unavailable, so the choice still applies for this session. */
let fallback = DEFAULT_MAX_EVENTS;
const listeners = new Set<() => void>();

/** How many events one day of the month grid shows before "+N" (per device). */
export function readMaxEvents(): number {
  try {
    const value = window.localStorage.getItem(MAX_EVENTS_KEY);
    return value === null ? DEFAULT_MAX_EVENTS : clampMaxEvents(value);
  } catch {
    return fallback;
  }
}

export function storeMaxEvents(value: number): void {
  const next = clampMaxEvents(value);
  fallback = next;
  try {
    window.localStorage.setItem(MAX_EVENTS_KEY, String(next));
  } catch {
    // Storage may be unavailable; the in-memory fallback keeps the choice for this session.
  }
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === MAX_EVENTS_KEY) notify();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(notify);
    window.removeEventListener('storage', onStorage);
  };
}

/** Current value plus a setter; every consumer re-renders on change (this tab and others). */
export function useMaxEvents(): [number, (value: number) => void] {
  const value = useSyncExternalStore(subscribe, readMaxEvents, () => DEFAULT_MAX_EVENTS);
  return [value, storeMaxEvents];
}
