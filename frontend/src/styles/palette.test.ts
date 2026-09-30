import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { CATEGORY_KEYS, CATEGORY_PALETTE, contrastRatio, type ColorMode } from './palette';

const css = readFileSync(resolve(process.cwd(), 'src/styles/palette.css'), 'utf8');
const MODES: ColorMode[] = ['light', 'dark'];
const pairs = CATEGORY_KEYS.flatMap((key) =>
  MODES.map((mode) => ({ key, mode, ...CATEGORY_PALETTE[key][mode] })),
);

describe('category palette', () => {
  it('has 12 keys and 24 pairs', () => {
    expect(CATEGORY_KEYS).toHaveLength(12);
    expect(pairs).toHaveLength(24);
  });

  it.each(pairs)('$key $mode text on fill meets WCAG AA (4.5:1)', ({ fill, text }) => {
    expect(contrastRatio(text, fill)).toBeGreaterThanOrEqual(4.5);
  });

  it('computes known contrast ratios', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
  });
});

function count(needle: string): number {
  return css.split(needle).length - 1;
}

describe('palette.css stays in sync with palette.ts', () => {
  it.each(pairs)('$key $mode variables match', ({ key, mode, fill, text }) => {
    // Light values appear once (:root); dark values twice (media query + explicit data-theme).
    const expected = mode === 'light' ? 1 : 2;
    expect(count(`--cat-${key}-fill: ${fill};`)).toBe(expected);
    expect(count(`--cat-${key}-text: ${text};`)).toBe(expected);
  });

  it('declares no unknown variables', () => {
    const declared = css.match(/--cat-[a-z]+-(fill|text):/g) ?? [];
    expect(declared).toHaveLength(CATEGORY_KEYS.length * 2 * 3);
  });
});
