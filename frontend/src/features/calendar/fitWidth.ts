import type { DayLayout } from './layout';

/** Horizontal padding of an event / holiday box (`padding: 0 4px`). */
const BOX_PADDING = 8;
/** Borders between halves and sub-pixel rounding: never let a title land exactly on the edge. */
const SLACK = 4;
/** The "+N" chip: 4px padding each side, 1px border each side, 2px from the cell edge. */
const CHIP_EXTRA = 12;

/** Fonts the grid draws event text with, as canvas `font` strings. */
export interface FitFonts {
  normal: string;
  italic: string;
  chip: string;
}

export interface TextMeasurer {
  text(value: string): number;
  italic(value: string): number;
  chip(value: string): number;
}

let context: CanvasRenderingContext2D | null | undefined;
const widths = new Map<string, number>();

function canvas(): CanvasRenderingContext2D | null {
  if (context === undefined) {
    try {
      context = document.createElement('canvas').getContext('2d');
    } catch {
      context = null;
    }
  }
  return context;
}

/** Width in px of `value` set in `font`; cached per (font, text) on one offscreen canvas. */
export function measureText(value: string, font: string): number {
  const key = `${font}\u0000${value}`;
  const cached = widths.get(key);
  if (cached !== undefined) return cached;
  const ctx = canvas();
  let width: number;
  if (ctx) {
    ctx.font = font;
    width = ctx.measureText(value).width;
  } else {
    // No canvas (very old browser): a generous per-character estimate.
    width = value.length * (parseFloat(/(\d+(?:\.\d+)?)px/.exec(font)?.[1] ?? '11') * 0.62);
  }
  widths.set(key, width);
  return width;
}

/** Letter spacing of vertical labels, in em (keep in sync with `.cal-vlabel-text`). */
const VLABEL_TRACKING = 0.02;
let vlabelFamily: string | null = null;

/**
 * Length of a vertical label's bold `title` in em, i.e. its length in px at a 1px font size.
 * CSS divides the block height by this to shrink long names until they fit.
 */
export function verticalLabelEm(title: string): number {
  if (vlabelFamily === null) {
    vlabelFamily =
      (typeof document !== 'undefined' && getComputedStyle(document.documentElement).fontFamily) ||
      'sans-serif';
  }
  const em = measureText(title, `700 100px ${vlabelFamily}`) / 100;
  return Math.max(0.5, em + VLABEL_TRACKING * title.length);
}

export function measurerFor(fonts: FitFonts): TextMeasurer {
  return {
    text: (value) => measureText(value, fonts.normal),
    italic: (value) => measureText(value, fonts.italic),
    chip: (value) => measureText(value, fonts.chip),
  };
}

/** The font the day cells are set in right now (follows theme, text size and loaded web fonts). */
export function readFitFonts(root: ParentNode | null): FitFonts | null {
  const cell = root?.querySelector<HTMLElement>('.cal-cell');
  if (!cell) return null;
  const style = getComputedStyle(cell);
  const size = parseFloat(style.fontSize) || 11;
  const weight = style.fontWeight || '400';
  const family = style.fontFamily || 'sans-serif';
  return {
    normal: `${weight} ${size}px ${family}`,
    italic: `italic ${weight} ${size}px ${family}`,
    // `.cal-more` is 0.5625rem against the cell's 0.6875rem.
    chip: `${weight} ${(size * 9) / 11}px ${family}`,
  };
}

/**
 * Width (px) the event area of one month column needs so that no title is truncated:
 * a full-width day needs its title; a split day needs twice its widest half (a half also
 * carries the "+N" chip when events overflow); a holiday on an empty day needs its name.
 *
 * @param holidays text drawn on days that have no events, by 1-based day of month
 */
export function monthFitWidth(
  layout: readonly DayLayout[],
  holidays: ReadonlyMap<number, string>,
  measure: TextMeasurer,
): number {
  let fit = 0;
  for (const d of layout) {
    if (d.total === 0) {
      const name = holidays.get(d.day);
      if (name) fit = Math.max(fit, measure.italic(name) + BOX_PADDING);
      continue;
    }
    // Titles are drawn on the first day of a block, except along a vertical label.
    const need = (lane: number) => {
      const p = d.lanes[lane];
      if (!p || !p.showTitle || (p.joinNext && p.input.labelVertical)) return 0;
      return measure.text(p.input.title) + BOX_PADDING;
    };
    if (d.total === 1) {
      fit = Math.max(fit, need(0), need(1));
      continue;
    }
    const chip = d.overflow > 0 ? measure.chip(`+${d.overflow}`) + CHIP_EXTRA : 0;
    fit = Math.max(fit, 2 * Math.max(need(0), need(1) + chip));
  }
  return fit === 0 ? 0 : Math.ceil(fit + SLACK);
}
