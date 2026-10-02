import { useRef, type TouchEvent } from 'react';
import { addDaysIso, isoWeekday, monthEndIso, monthStartIso, splitIso } from '../../../lib/dates';

export type MobileView = 'day' | 'month';

const VIEW_KEY = 'hoje.calendar.mobileView';

/** Last chosen mobile view; storage may be missing or throw (private mode), then `day`. */
export function loadView(): MobileView {
  try {
    return window.localStorage.getItem(VIEW_KEY) === 'month' ? 'month' : 'day';
  } catch {
    return 'day';
  }
}

export function saveView(view: MobileView): void {
  try {
    window.localStorage.setItem(VIEW_KEY, view);
  } catch {
    // Remembering the view is a nicety; ignore storage failures.
  }
}

/** Monday of the week containing `iso`. */
export function weekStart(iso: string): string {
  return addDaysIso(iso, 1 - isoWeekday(iso));
}

export function weekDays(iso: string): string[] {
  const start = weekStart(iso);
  return Array.from({ length: 7 }, (_, i) => addDaysIso(start, i));
}

/** Range requested for the day view: the selected week plus a week either side. */
export function dayRange(selected: string): { from: string; to: string } {
  const start = weekStart(selected);
  return { from: addDaysIso(start, -7), to: addDaysIso(start, 13) };
}

/** Range requested for the month view: the whole month of `selected`. */
export function monthRange(selected: string): { from: string; to: string } {
  const [year, month] = splitIso(selected);
  return { from: monthStartIso(year, month), to: monthEndIso(year, month) };
}

/** Horizontal swipe detection: `onSwipe(1)` for a swipe left (forward), `-1` for right. */
export function useSwipe(onSwipe: (direction: -1 | 1) => void) {
  const start = useRef<{ x: number; y: number } | null>(null);
  return {
    onTouchStart(event: TouchEvent) {
      const t = event.touches[0];
      start.current = t ? { x: t.clientX, y: t.clientY } : null;
    },
    onTouchEnd(event: TouchEvent) {
      const origin = start.current;
      const t = event.changedTouches[0];
      start.current = null;
      if (!origin || !t) return;
      const dx = t.clientX - origin.x;
      const dy = t.clientY - origin.y;
      if (Math.abs(dx) >= 50 && Math.abs(dx) > Math.abs(dy) * 1.5) onSwipe(dx < 0 ? 1 : -1);
    },
  };
}
