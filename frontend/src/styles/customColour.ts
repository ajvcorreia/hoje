import type { CSSProperties } from 'react';
import { contrastRatio, isCategoryKey, type CategoryColor, type ColorMode } from './palette';

/**
 * A category colour is either a palette key or any `#rrggbb`. For a custom colour this derives
 * the same fill/text pair per theme that the palette hand-picks, so the calendar renders it the
 * way it renders a named colour: AA (4.5:1) in light and dark, AAA (7:1) in light-contrast.
 */
const HEX = /^#[0-9a-f]{6}$/i;
const AA = 4.5;
const AAA = 7;

type Rgb = [number, number, number];

export const isHex = (value: string | null | undefined): boolean =>
  typeof value === 'string' && HEX.test(value);

const toRgb = (hex: string): Rgb => {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const toHex = (rgb: Rgb) =>
  '#' +
  rgb
    .map((c) =>
      Math.round(Math.min(255, Math.max(0, c)))
        .toString(16)
        .padStart(2, '0'),
    )
    .join('');

/** `a` moved `amount` (0..1) of the way to `b`. */
const mix = (a: Rgb, b: Rgb, amount: number): Rgb => [
  a[0] + (b[0] - a[0]) * amount,
  a[1] + (b[1] - a[1]) * amount,
  a[2] + (b[2] - a[2]) * amount,
];

const BLACK: Rgb = [0, 0, 0];
const WHITE: Rgb = [255, 255, 255];

/** Move `text` towards `limit` in small steps until it reads on `fill` at `min`:1 (or reaches it). */
function readable(text: Rgb, fill: string, limit: Rgb, min: number): string {
  for (let step = 0; step <= 20; step++) {
    const candidate = toHex(mix(text, limit, step / 20));
    if (contrastRatio(candidate, fill) >= min) return candidate;
  }
  return toHex(limit);
}

/** The fill and text of a custom colour in each theme. */
export function customColour(hex: string): Record<ColorMode, CategoryColor> {
  const base = toRgb(hex);
  const lightFill = toHex(mix(base, WHITE, 0.82));
  const contrastFill = toHex(mix(base, WHITE, 0.75));
  const darkFill = toHex(mix(base, BLACK, 0.62));
  return {
    light: { fill: lightFill, text: readable(base, lightFill, BLACK, AA) },
    dark: { fill: darkFill, text: readable(mix(base, WHITE, 0.7), darkFill, WHITE, AA) },
    'light-contrast': { fill: contrastFill, text: readable(base, contrastFill, BLACK, AAA) },
  };
}

/**
 * Props that colour an element with a category colour: `data-cat` for a palette key, and for a
 * custom colour `data-cat="custom"` plus the derived tokens (`calendar.css` picks the theme's).
 */
export function catProps(colour: string | null | undefined): {
  'data-cat'?: string;
  style?: CSSProperties;
} {
  if (!colour) return {};
  if (isCategoryKey(colour) || !isHex(colour)) return { 'data-cat': colour };
  const tokens = customColour(colour);
  return {
    'data-cat': 'custom',
    style: {
      '--cc-light-fill': tokens.light.fill,
      '--cc-light-text': tokens.light.text,
      '--cc-dark-fill': tokens.dark.fill,
      '--cc-dark-text': tokens.dark.text,
      '--cc-contrast-fill': tokens['light-contrast'].fill,
      '--cc-contrast-text': tokens['light-contrast'].text,
    } as CSSProperties,
  };
}
