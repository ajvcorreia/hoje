/**
 * Source of truth for the category palette. `palette.css` mirrors these values
 * (a unit test keeps them in sync) and every fill/text pair must reach WCAG AA (4.5:1).
 * The backend stores only the key, never a hex value.
 */
export const CATEGORY_KEYS = [
  'slate',
  'red',
  'orange',
  'amber',
  'lime',
  'green',
  'teal',
  'cyan',
  'blue',
  'indigo',
  'violet',
  'pink',
] as const;

export type CategoryKey = (typeof CATEGORY_KEYS)[number];
export type ColorMode = 'light' | 'dark';
export interface CategoryColor {
  fill: string;
  text: string;
}

export const CATEGORY_PALETTE: Record<CategoryKey, Record<ColorMode, CategoryColor>> = {
  slate: {
    light: { fill: '#e2e8f0', text: '#1e293b' },
    dark: { fill: '#334155', text: '#e2e8f0' },
  },
  red: {
    light: { fill: '#fee2e2', text: '#991b1b' },
    dark: { fill: '#7f1d1d', text: '#fecaca' },
  },
  orange: {
    light: { fill: '#ffedd5', text: '#9a3412' },
    dark: { fill: '#7c2d12', text: '#fed7aa' },
  },
  amber: {
    light: { fill: '#fef3c7', text: '#92400e' },
    dark: { fill: '#78350f', text: '#fde68a' },
  },
  lime: {
    light: { fill: '#ecfccb', text: '#3f6212' },
    dark: { fill: '#365314', text: '#d9f99d' },
  },
  green: {
    light: { fill: '#dcfce7', text: '#166534' },
    dark: { fill: '#14532d', text: '#bbf7d0' },
  },
  teal: {
    light: { fill: '#ccfbf1', text: '#115e59' },
    dark: { fill: '#134e4a', text: '#99f6e4' },
  },
  cyan: {
    light: { fill: '#cffafe', text: '#155e75' },
    dark: { fill: '#164e63', text: '#a5f3fc' },
  },
  blue: {
    light: { fill: '#dbeafe', text: '#1e40af' },
    dark: { fill: '#1e3a8a', text: '#bfdbfe' },
  },
  indigo: {
    light: { fill: '#e0e7ff', text: '#3730a3' },
    dark: { fill: '#312e81', text: '#c7d2fe' },
  },
  violet: {
    light: { fill: '#ede9fe', text: '#5b21b6' },
    dark: { fill: '#4c1d95', text: '#ddd6fe' },
  },
  pink: {
    light: { fill: '#fce7f3', text: '#9d174d' },
    dark: { fill: '#831843', text: '#fbcfe8' },
  },
};

export function isCategoryKey(value: string): value is CategoryKey {
  return (CATEGORY_KEYS as readonly string[]).includes(value);
}

/** WCAG 2.x relative luminance of a #rrggbb colour. */
export function relativeLuminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m?.[1]) throw new Error(`Invalid hex colour: ${hex}`);
  const n = parseInt(m[1], 16);
  const lin = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * (lin[0] ?? 0) + 0.7152 * (lin[1] ?? 0) + 0.0722 * (lin[2] ?? 0);
}

/** WCAG contrast ratio between two #rrggbb colours (1..21). */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}
