import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  MULTIDAY_LABELS_KEY,
  readMultidayLabelMode,
  storeMultidayLabelMode,
  useMultidayLabelMode,
} from './multidayLabels';

afterEach(() => {
  vi.restoreAllMocks();
  storeMultidayLabelMode('horizontal');
});

describe('multi-day label mode', () => {
  it('defaults to horizontal and ignores invalid values', () => {
    window.localStorage.removeItem(MULTIDAY_LABELS_KEY);
    expect(readMultidayLabelMode()).toBe('horizontal');
    window.localStorage.setItem(MULTIDAY_LABELS_KEY, 'diagonal');
    expect(readMultidayLabelMode()).toBe('horizontal');
  });

  it('persists and re-renders subscribers', () => {
    const { result } = renderHook(() => useMultidayLabelMode());
    expect(result.current[0]).toBe('horizontal');
    act(() => result.current[1]('vertical'));
    expect(result.current[0]).toBe('vertical');
    expect(window.localStorage.getItem(MULTIDAY_LABELS_KEY)).toBe('vertical');
  });

  it('follows changes made in another tab', () => {
    const { result } = renderHook(() => useMultidayLabelMode());
    act(() => {
      window.localStorage.setItem(MULTIDAY_LABELS_KEY, 'vertical');
      window.dispatchEvent(new StorageEvent('storage', { key: MULTIDAY_LABELS_KEY }));
    });
    expect(result.current[0]).toBe('vertical');
  });

  it('tolerates localStorage failures and keeps the choice in memory', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readMultidayLabelMode()).toBe('horizontal');
    expect(() => storeMultidayLabelMode('vertical')).not.toThrow();
    expect(readMultidayLabelMode()).toBe('vertical');
  });
});
