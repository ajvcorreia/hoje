import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { CATEGORY_KEYS, CATEGORY_PALETTE, contrastRatio, type ColorMode } from './palette';

const css = readFileSync(resolve(process.cwd(), 'src/styles/palette.css'), 'utf8');
const tokensCss = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8');
const MODES: ColorMode[] = ['light', 'dark', 'light-contrast'];
const pairs = CATEGORY_KEYS.flatMap((key) =>
  MODES.map((mode) => ({ key, mode, ...CATEGORY_PALETTE[key][mode] })),
);
const aaPairs = pairs.filter((p) => p.mode !== 'light-contrast');
const aaaPairs = pairs.filter((p) => p.mode === 'light-contrast');

describe('category palette', () => {
  it('has 20 keys and 60 pairs, original twelve first', () => {
    expect(CATEGORY_KEYS).toHaveLength(20);
    expect(pairs).toHaveLength(60);
    expect(CATEGORY_KEYS.slice(0, 12).join(' ')).toBe(
      'slate red orange amber lime green teal cyan blue indigo violet pink',
    );
    expect(CATEGORY_KEYS.slice(12).join(' ')).toBe(
      'rose fuchsia purple sky emerald yellow brown gray',
    );
  });

  it.each(aaPairs)('$key $mode text on fill meets WCAG AA (4.5:1)', ({ fill, text }) => {
    expect(contrastRatio(text, fill)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(aaaPairs)('$key $mode text on fill meets WCAG AAA (7:1)', ({ fill, text }) => {
    expect(contrastRatio(text, fill)).toBeGreaterThanOrEqual(7);
  });

  it.each(aaaPairs)(
    '$key $mode outline colour is AAA against white and the fill is not white',
    ({ fill, text }) => {
      expect(contrastRatio(text, '#ffffff')).toBeGreaterThanOrEqual(7);
      expect(fill).not.toBe('#ffffff');
    },
  );

  it('keeps high-contrast fills distinct from each other', () => {
    const fills = CATEGORY_KEYS.map((k) => CATEGORY_PALETTE[k]['light-contrast'].fill);
    expect(new Set(fills).size).toBe(fills.length);
  });

  it('computes known contrast ratios', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
  });
});

/** Declarations of the rule whose selector contains `selector`. */
function block(source: string, selector: string): string {
  const start = source.indexOf(selector);
  if (start < 0) throw new Error(`No rule for ${selector}`);
  return source.slice(source.indexOf('{', start), source.indexOf('}', start));
}

const BLOCKS: Record<ColorMode, string[]> = {
  light: [block(css, ':root {')],
  dark: [
    block(css, "@media (prefers-color-scheme: dark) {\n  :root:not([data-theme='light'])"),
    block(css, ":root[data-theme='dark']"),
  ],
  'light-contrast': [block(css, ":root[data-theme='light-contrast']")],
};

describe('palette.css stays in sync with palette.ts', () => {
  it.each(pairs)('$key $mode variables match', ({ key, mode, fill, text }) => {
    for (const rule of BLOCKS[mode]) {
      expect(rule).toContain(`--cat-${key}-fill: ${fill};`);
      expect(rule).toContain(`--cat-${key}-text: ${text};`);
    }
  });

  it('declares no unknown variables', () => {
    const declared = css.match(/--cat-[a-z]+-(fill|text):/g) ?? [];
    // light + media dark + explicit dark + light-contrast
    expect(declared).toHaveLength(CATEGORY_KEYS.length * 2 * 4);
  });

  it('excludes both light themes from the dark media query', () => {
    expect(css).toContain(":root:not([data-theme='light']):not([data-theme='light-contrast'])");
    expect(tokensCss).toContain(
      ":root:not([data-theme='light']):not([data-theme='light-contrast'])",
    );
  });
});

describe('light-contrast tokens', () => {
  const rule = block(tokensCss, ":root[data-theme='light-contrast']");
  const token = (name: string) => {
    const m = new RegExp(`--${name}: (#[0-9a-f]{6});`, 'i').exec(rule);
    if (!m?.[1]) throw new Error(`Missing token ${name}`);
    return m[1];
  };

  it('declares a light colour scheme', () => {
    expect(rule).toContain('color-scheme: light;');
  });

  it.each([
    ['text', 'surface'],
    ['text', 'surface-muted'],
    ['text', 'today'],
    ['text', 'weekend'],
    ['text-muted', 'surface'],
    ['text-muted', 'surface-muted'],
    ['text-muted', 'weekend'],
    ['text-muted', 'today'],
    ['accent', 'surface'],
    ['accent', 'weekend'],
    ['danger', 'surface'],
    ['danger', 'surface-muted'],
    ['accent-contrast', 'accent'],
  ])('%s on %s reaches AAA (7:1)', (fg, bg) => {
    expect(contrastRatio(token(fg), token(bg))).toBeGreaterThanOrEqual(7);
  });

  it.each(['border', 'border-strong', 'month-outline', 'accent'])(
    '%s is a 3:1 boundary against the surface',
    (name) => {
      expect(contrastRatio(token(name), token('surface'))).toBeGreaterThanOrEqual(3);
    },
  );

  it('has pure white surfaces', () => {
    expect(token('surface')).toBe('#ffffff');
  });
});
