/**
 * Source of truth for the category palette. `palette.css` mirrors these values
 * (a unit test keeps them in sync). Every fill/text pair must reach WCAG AA (4.5:1);
 * the `light-contrast` theme must reach AAA (7:1).
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
  'rose',
  'fuchsia',
  'purple',
  'sky',
  'emerald',
  'yellow',
  'brown',
  'gray',
] as const;

export type CategoryKey = (typeof CATEGORY_KEYS)[number];
export type ColorMode = 'light' | 'dark' | 'light-contrast';
export interface CategoryColor {
  fill: string;
  text: string;
}

export const CATEGORY_PALETTE: Record<CategoryKey, Record<ColorMode, CategoryColor>> = {
  slate: {
    light: { fill: '#e2e8f0', text: '#1e293b' },
    dark: { fill: '#334155', text: '#e2e8f0' },
    'light-contrast': { fill: '#cbd5e1', text: '#020617' },
  },
  red: {
    light: { fill: '#fee2e2', text: '#991b1b' },
    dark: { fill: '#7f1d1d', text: '#fecaca' },
    'light-contrast': { fill: '#fecaca', text: '#450a0a' },
  },
  orange: {
    light: { fill: '#ffedd5', text: '#9a3412' },
    dark: { fill: '#7c2d12', text: '#fed7aa' },
    'light-contrast': { fill: '#fed7aa', text: '#431407' },
  },
  amber: {
    light: { fill: '#fef3c7', text: '#92400e' },
    dark: { fill: '#78350f', text: '#fde68a' },
    'light-contrast': { fill: '#fde68a', text: '#451a03' },
  },
  lime: {
    light: { fill: '#ecfccb', text: '#3f6212' },
    dark: { fill: '#365314', text: '#d9f99d' },
    'light-contrast': { fill: '#d9f99d', text: '#1a2e05' },
  },
  green: {
    light: { fill: '#dcfce7', text: '#166534' },
    dark: { fill: '#14532d', text: '#bbf7d0' },
    'light-contrast': { fill: '#bbf7d0', text: '#052e16' },
  },
  teal: {
    light: { fill: '#ccfbf1', text: '#115e59' },
    dark: { fill: '#134e4a', text: '#99f6e4' },
    'light-contrast': { fill: '#99f6e4', text: '#042f2e' },
  },
  cyan: {
    light: { fill: '#cffafe', text: '#155e75' },
    dark: { fill: '#164e63', text: '#a5f3fc' },
    'light-contrast': { fill: '#a5f3fc', text: '#083344' },
  },
  blue: {
    light: { fill: '#dbeafe', text: '#1e40af' },
    dark: { fill: '#1e3a8a', text: '#bfdbfe' },
    'light-contrast': { fill: '#bfdbfe', text: '#172554' },
  },
  indigo: {
    light: { fill: '#e0e7ff', text: '#3730a3' },
    dark: { fill: '#312e81', text: '#c7d2fe' },
    'light-contrast': { fill: '#c7d2fe', text: '#1e1b4b' },
  },
  violet: {
    light: { fill: '#ede9fe', text: '#5b21b6' },
    dark: { fill: '#4c1d95', text: '#ddd6fe' },
    'light-contrast': { fill: '#ddd6fe', text: '#2e1065' },
  },
  pink: {
    light: { fill: '#fce7f3', text: '#9d174d' },
    dark: { fill: '#831843', text: '#fbcfe8' },
    'light-contrast': { fill: '#fbcfe8', text: '#500724' },
  },
  rose: {
    light: { fill: '#ffe4e6', text: '#9f1239' },
    dark: { fill: '#881337', text: '#fecdd3' },
    'light-contrast': { fill: '#fecdd3', text: '#4c0519' },
  },
  fuchsia: {
    light: { fill: '#fae8ff', text: '#86198f' },
    dark: { fill: '#701a75', text: '#f5d0fe' },
    'light-contrast': { fill: '#f5d0fe', text: '#4a044e' },
  },
  purple: {
    light: { fill: '#f3e8ff', text: '#6b21a8' },
    dark: { fill: '#581c87', text: '#e9d5ff' },
    'light-contrast': { fill: '#e9d5ff', text: '#3b0764' },
  },
  sky: {
    light: { fill: '#e0f2fe', text: '#075985' },
    dark: { fill: '#0c4a6e', text: '#bae6fd' },
    'light-contrast': { fill: '#bae6fd', text: '#082f49' },
  },
  emerald: {
    light: { fill: '#d1fae5', text: '#065f46' },
    dark: { fill: '#064e3b', text: '#a7f3d0' },
    'light-contrast': { fill: '#a7f3d0', text: '#022c22' },
  },
  yellow: {
    light: { fill: '#fef9c3', text: '#854d0e' },
    dark: { fill: '#713f12', text: '#fef08a' },
    'light-contrast': { fill: '#fef08a', text: '#422006' },
  },
  brown: {
    light: { fill: '#efe3d6', text: '#6b3f1d' },
    dark: { fill: '#4a2c17', text: '#e8d0b8' },
    'light-contrast': { fill: '#e3cdb4', text: '#2b1708' },
  },
  gray: {
    light: { fill: '#e5e5e5', text: '#262626' },
    dark: { fill: '#404040', text: '#e5e5e5' },
    'light-contrast': { fill: '#d4d4d4', text: '#171717' },
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
