import { useSyncExternalStore } from 'react';

export const PILLS_POSITIONS = ['top', 'bottom', 'left', 'right'] as const;
export type PillsPosition = (typeof PILLS_POSITIONS)[number];

export const PILLS_POSITION_KEY = 'hoje.pillsPosition';

const DEFAULT: PillsPosition = 'top';

export function isPillsPosition(value: unknown): value is PillsPosition {
  return typeof value === 'string' && (PILLS_POSITIONS as readonly string[]).includes(value);
}

/** Used when localStorage is unavailable, so the choice still applies for this session. */
let fallback: PillsPosition = DEFAULT;
const listeners = new Set<() => void>();

export function readPillsPosition(): PillsPosition {
  try {
    const value = window.localStorage.getItem(PILLS_POSITION_KEY);
    return isPillsPosition(value) ? value : DEFAULT;
  } catch {
    return fallback;
  }
}

export function storePillsPosition(position: PillsPosition): void {
  fallback = position;
  try {
    window.localStorage.setItem(PILLS_POSITION_KEY, position);
  } catch {
    // Storage may be unavailable; the in-memory fallback keeps the choice for this session.
  }
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === PILLS_POSITION_KEY) notify();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(notify);
    window.removeEventListener('storage', onStorage);
  };
}

/** Where the desktop calendar puts the category filter pills (per device; top by default). */
export function usePillsPosition(): [PillsPosition, (position: PillsPosition) => void] {
  const position = useSyncExternalStore(subscribe, readPillsPosition, () => DEFAULT);
  return [position, storePillsPosition];
}
