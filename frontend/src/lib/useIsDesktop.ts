import { useSyncExternalStore } from 'react';

const QUERY = '(min-width: 768px)';

function subscribe(callback: () => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => undefined;
  const mql = window.matchMedia(QUERY);
  mql.addEventListener('change', callback);
  return () => mql.removeEventListener('change', callback);
}

function snapshot(): boolean {
  // jsdom and very old browsers have no matchMedia: assume desktop.
  return typeof window.matchMedia === 'function' ? window.matchMedia(QUERY).matches : true;
}

/** True at >= 768 px (the desktop/tablet calendar); false on phones. */
export function useIsDesktop(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => true);
}
