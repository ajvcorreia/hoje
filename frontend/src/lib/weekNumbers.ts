import { useSyncExternalStore } from 'react';

export const WEEK_NUMBERS_KEY = 'hoje.weekNumbers';

/** Used when localStorage is unavailable, so the choice still applies for this session. */
let fallback = true;
const listeners = new Set<() => void>();

/** Week numbers are shown unless explicitly switched off. */
export function readWeekNumbers(): boolean {
  try {
    const value = window.localStorage.getItem(WEEK_NUMBERS_KEY);
    return value === null ? true : value !== 'off';
  } catch {
    return fallback;
  }
}

export function storeWeekNumbers(show: boolean): void {
  fallback = show;
  try {
    window.localStorage.setItem(WEEK_NUMBERS_KEY, show ? 'on' : 'off');
  } catch {
    // Storage may be unavailable; the in-memory fallback keeps the choice for this session.
  }
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === WEEK_NUMBERS_KEY) notify();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(notify);
    window.removeEventListener('storage', onStorage);
  };
}

/** Current value plus a setter; every consumer re-renders on change (this tab and others). */
export function useWeekNumbers(): [boolean, (show: boolean) => void] {
  const show = useSyncExternalStore(subscribe, readWeekNumbers, () => true);
  return [show, storeWeekNumbers];
}
