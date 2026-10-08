import { useEffect, useState } from 'react';
import { todayIso } from './dates';

/** Milliseconds from `now` to the next local midnight (DST-safe: built from calendar fields). */
export function msUntilMidnight(now = new Date()): number {
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return Math.max(next.getTime() - now.getTime(), 0);
}

/**
 * Today as `yyyy-MM-dd`, kept current for tabs left open across midnight: it re-renders the
 * caller when the local day changes (timer armed for the next midnight) and re-checks when the
 * tab becomes visible or focused again, since timers are throttled or frozen while hidden/asleep.
 */
export function useToday(): string {
  const [today, setToday] = useState(todayIso);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      clearTimeout(timer);
      // A little past midnight so the clock is certainly on the new day when it fires.
      timer = setTimeout(sync, msUntilMidnight() + 100);
    };
    const sync = () => {
      setToday(todayIso()); // same string -> no re-render
      arm();
    };
    const onVisibility = () => {
      if (document.visibilityState !== 'hidden') sync();
    };
    arm();
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('focus', sync);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', sync);
    };
  }, []);

  return today;
}
