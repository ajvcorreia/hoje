import { describe, expect, it } from 'vitest';
import { centerScrollLeft } from './centerScroll';

describe('centerScrollLeft', () => {
  it('puts the column centre at the viewport centre', () => {
    // column 1000..1200 (centre 1100) in a 600 wide viewport -> viewport 800..1400
    expect(centerScrollLeft(1000, 200, 600, 3000)).toBe(800);
  });
  it('clamps at the start', () => {
    expect(centerScrollLeft(40, 200, 600, 3000)).toBe(0);
  });
  it('clamps at the end', () => {
    expect(centerScrollLeft(2800, 200, 600, 3000)).toBe(2400);
  });
  it('is 0 when nothing scrolls', () => {
    expect(centerScrollLeft(500, 200, 600, 600)).toBe(0);
    expect(centerScrollLeft(500, 200, 600, 400)).toBe(0);
  });
});
