import { afterEach, describe, expect, it, vi } from 'vitest';
import { WEEK_NUMBERS_KEY, readWeekNumbers, storeWeekNumbers } from './weekNumbers';

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  storeWeekNumbers(true);
});

describe('week numbers preference', () => {
  it('defaults to on and round-trips', () => {
    window.localStorage.clear();
    expect(readWeekNumbers()).toBe(true);
    storeWeekNumbers(false);
    expect(window.localStorage.getItem(WEEK_NUMBERS_KEY)).toBe('off');
    expect(readWeekNumbers()).toBe(false);
  });

  it('tolerates localStorage failures', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => storeWeekNumbers(false)).not.toThrow();
    expect(readWeekNumbers()).toBe(false);
  });
});
