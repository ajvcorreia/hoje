import { useEffect } from 'react';
import { useAuthState } from '../app/useAuthState';
import { useMeSetting } from './meSetting';

/** How round the corners are across the app (stored on the account; same list as the API). */
export const CORNERS = ['none', 'small', 'medium', 'large', 'xlarge'] as const;
export type Corners = (typeof CORNERS)[number];

/** Today's look: Tailwind's own radii (see index.css). */
export const DEFAULT_CORNERS: Corners = 'medium';

export const CORNERS_STORAGE_KEY = 'hoje.corners';

export const isCorners = (value: unknown): value is Corners =>
  typeof value === 'string' && (CORNERS as readonly string[]).includes(value);

export function readStoredCorners(): Corners {
  try {
    const value = window.localStorage.getItem(CORNERS_STORAGE_KEY);
    return isCorners(value) ? value : DEFAULT_CORNERS;
  } catch {
    return DEFAULT_CORNERS;
  }
}

/** Sets `data-corners` on <html> (CSS scales every radius from it) and keeps a device copy. */
export function applyCorners(corners: Corners): void {
  document.documentElement.setAttribute('data-corners', corners);
  try {
    window.localStorage.setItem(CORNERS_STORAGE_KEY, corners);
  } catch {
    // Storage may be unavailable; the account still has the choice.
  }
}

/** The corner size, saved on the account; applied at once on this device. */
export function useCorners(): [Corners, (value: Corners) => void] {
  const [value, setValue] = useMeSetting('corner_radius', DEFAULT_CORNERS);
  const corners = isCorners(value) ? value : DEFAULT_CORNERS;
  const set = (next: Corners) => {
    applyCorners(next);
    setValue(next);
  };
  return [corners, set];
}

/** Keeps this device on the account's corner size (on sign-in and changes from other devices). */
export function useCornersSync(): void {
  const { data } = useAuthState();
  const account = data?.user?.corner_radius;
  useEffect(() => {
    if (isCorners(account)) applyCorners(account);
  }, [account]);
}
