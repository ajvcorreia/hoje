import { useSyncExternalStore } from 'react';

/** A per-device on/off display preference stored in localStorage as `on` / `off`. */
export interface BooleanPreference {
  key: string;
  read(): boolean;
  store(value: boolean): void;
  /** Current value plus a setter; every consumer re-renders on change (this tab and others). */
  use(): [boolean, (value: boolean) => void];
}

export function createBooleanPreference(key: string, defaultValue: boolean): BooleanPreference {
  /** Used when localStorage is unavailable, so the choice still applies for this session. */
  let fallback = defaultValue;
  const listeners = new Set<() => void>();

  function read(): boolean {
    try {
      const value = window.localStorage.getItem(key);
      if (value === 'on') return true;
      if (value === 'off') return false;
      return defaultValue;
    } catch {
      return fallback;
    }
  }

  function store(value: boolean): void {
    fallback = value;
    try {
      window.localStorage.setItem(key, value ? 'on' : 'off');
    } catch {
      // Storage may be unavailable; the in-memory fallback keeps the choice for this session.
    }
    listeners.forEach((notify) => notify());
  }

  function subscribe(notify: () => void): () => void {
    listeners.add(notify);
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === key) notify();
    };
    window.addEventListener('storage', onStorage);
    return () => {
      listeners.delete(notify);
      window.removeEventListener('storage', onStorage);
    };
  }

  function use(): [boolean, (value: boolean) => void] {
    const value = useSyncExternalStore(subscribe, read, () => defaultValue);
    return [value, store];
  }

  return { key, read, store, use };
}
