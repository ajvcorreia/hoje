import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { msUntilMidnight, useToday } from './useToday';

let visibility: 'visible' | 'hidden' = 'visible';

beforeEach(() => {
  visibility = 'visible';
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility });
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 9, 8, 23, 59, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('msUntilMidnight', () => {
  it('counts to the next local midnight', () => {
    expect(msUntilMidnight(new Date(2026, 9, 8, 23, 59, 0))).toBe(60_000);
    expect(msUntilMidnight(new Date(2026, 9, 8, 0, 0, 0))).toBe(24 * 3_600_000);
  });
});

describe('useToday', () => {
  it('rolls over at local midnight without a reload', () => {
    const { result } = renderHook(() => useToday());
    expect(result.current).toBe('2026-10-08');
    act(() => {
      vi.advanceTimersByTime(59_000);
    });
    expect(result.current).toBe('2026-10-08');
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current).toBe('2026-10-09');
    // Re-armed for the following midnight.
    act(() => {
      vi.advanceTimersByTime(24 * 3_600_000);
    });
    expect(result.current).toBe('2026-10-10');
  });

  it('re-checks when the tab becomes visible after a frozen timer', () => {
    const { result } = renderHook(() => useToday());
    act(() => {
      visibility = 'hidden';
      document.dispatchEvent(new Event('visibilitychange'));
    });
    // Jump the clock without firing timers (sleeping laptop).
    vi.setSystemTime(new Date(2026, 9, 10, 8, 0, 0));
    expect(result.current).toBe('2026-10-08');
    act(() => {
      visibility = 'visible';
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(result.current).toBe('2026-10-10');
  });

  it('re-checks when the window regains focus', () => {
    const { result } = renderHook(() => useToday());
    vi.setSystemTime(new Date(2026, 9, 9, 7, 0, 0));
    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    expect(result.current).toBe('2026-10-09');
  });

  it('stops its timer and listeners on unmount', () => {
    const { unmount } = renderHook(() => useToday());
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
