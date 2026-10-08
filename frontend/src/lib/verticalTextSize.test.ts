import { describe, expect, it } from 'vitest';
import { DEFAULT_VERTICAL_TEXT_SIZE, clampVerticalTextSize } from './verticalTextSize';

describe('vertical text size', () => {
  it('defaults to 12px, the size rotated labels always had', () => {
    expect(DEFAULT_VERTICAL_TEXT_SIZE).toBe(12);
  });

  it('clamps to 8-32 and ignores garbage', () => {
    expect(clampVerticalTextSize(7)).toBe(8);
    expect(clampVerticalTextSize(99)).toBe(32);
    expect(clampVerticalTextSize(13.4)).toBe(13);
    expect(clampVerticalTextSize('abc')).toBe(DEFAULT_VERTICAL_TEXT_SIZE);
    expect(clampVerticalTextSize(undefined)).toBe(DEFAULT_VERTICAL_TEXT_SIZE);
  });
});
