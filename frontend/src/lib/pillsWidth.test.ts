import { afterEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_PILLS_WIDTH,
  MAX_PILLS_WIDTH,
  MIN_PILLS_WIDTH,
  PILLS_WIDTH_KEY,
  clampPillsWidth,
  readPillsWidth,
  storePillsWidth,
} from './pillsWidth';

describe('pills width', () => {
  afterEach(() => window.localStorage.clear());

  it('clamps to the range and falls back to the default', () => {
    expect(clampPillsWidth(3)).toBe(MIN_PILLS_WIDTH);
    expect(clampPillsWidth(99)).toBe(MAX_PILLS_WIDTH);
    expect(clampPillsWidth('12.4')).toBe(12);
    expect(clampPillsWidth('wide')).toBe(DEFAULT_PILLS_WIDTH);
    expect(clampPillsWidth(null)).toBe(DEFAULT_PILLS_WIDTH);
  });

  it('is the default until chosen, then remembers the choice', () => {
    expect(readPillsWidth()).toBe(DEFAULT_PILLS_WIDTH);
    storePillsWidth(14);
    expect(readPillsWidth()).toBe(14);
    expect(window.localStorage.getItem(PILLS_WIDTH_KEY)).toBe('14');
  });
});
