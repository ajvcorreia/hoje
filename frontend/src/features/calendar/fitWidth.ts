import { dayMode, type DayLayout, type Placed } from './layout';

/** Horizontal padding of an event / holiday box (`padding: 0 4px`). */
const BOX_PADDING = 8;
/** Borders between lanes and sub-pixel rounding: never let a title land exactly on the edge. */
const SLACK = 4;
/** The "+N" chip: 4px padding each side, 1px border each side, 2px from the cell edge. */
const CHIP_EXTRA = 12;
/** Width of one rotated label column: the line height of its smallest comfortable text (0.75rem x 1.15). */
const VLABEL_LANE = 16;
/** A lane column is never narrower than this, so even a block without a title stays visible. */
const LANE_MIN = 12;

/** Fonts the grid draws event text with, as canvas `font` strings. */
export interface FitFonts {
  normal: string;
  italic: string;
  chip: string;
}

/** Used until the grid has read the real cell font. */
export const DEFAULT_FIT_FONTS: FitFonts = {
  normal: '400 11px sans-serif',
  italic: 'italic 400 11px sans-serif',
  chip: '400 9px sans-serif',
};

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

/** Track widths (px) of one month column's event area; see {@link monthTracks}. */
export interface MonthTracks {
  /** Holiday / birthday track before the lanes on days with events; 0 when the month has none. */
  overlay: number;
  /** One entry per lane column: the widest title (or rotated label) of that lane in the month. */
  lanes: number[];
  /** "+N" chip track after the lanes; 0 when no day overflows. */
  chip: number;
  /** Minimum width of the whole event area, slack included. */
  width: number;
  /** Nothing but rotated labels: the month needs no horizontal-text minimum. */
  onlyVertical: boolean;
}

/** A block drawn as a rotated label (it spans 2+ days of this month and is flagged). */
const isVertical = (p: Placed) => !!p.input.labelVertical && (p.joinNext || p.joinPrev);

/**
 * Widths one month column needs so that nothing is cut off. A day's content sits in one row:
 * day number, then the holiday / birthday text, then the lanes side by side, then the "+N" chip.
 * A day with a single event and no overlay uses the whole cell and needs just that title; an
 * empty day with an overlay needs the overlay text. Every other day shares the month's tracks, so
 * lane `i` has the same width and position on all of them (and rotated labels can follow it):
 * the widest overlay, the widest title per lane and the widest chip of the month. A rotated
 * label needs one line height per lane it sits in, not its text width.
 *
 * @param overlays holiday / birthday text by 1-based day of month
 */
export function monthTracks(
  layout: readonly DayLayout[],
  overlays: ReadonlyMap<number, string>,
  measure: TextMeasurer,
): MonthTracks {
  const titleNeed = (p: Placed) => {
    if (isVertical(p)) return VLABEL_LANE;
    return p.showTitle ? measure.text(p.input.title) + BOX_PADDING : 0;
  };
  let single = 0;
  let overlay = 0;
  let chip = 0;
  let rows = false;
  let text = false;
  const lanes: number[] = [];
  for (const d of layout) {
    const name = overlays.get(d.day);
    const nameWidth = name ? measure.italic(name) + BOX_PADDING : 0;
    if (name) text = true;
    const mode = dayMode(d, name !== undefined);
    if (mode === 'empty') {
      single = Math.max(single, nameWidth);
      continue;
    }
    for (const p of d.lanes) if (p && p.showTitle && !isVertical(p)) text = true;
    if (mode === 'full') {
      single = Math.max(single, ...d.lanes.map((p) => (p ? titleNeed(p) : 0)));
      continue;
    }
    rows = true;
    overlay = Math.max(overlay, nameWidth);
    d.lanes.forEach((p, l) => {
      if (p) lanes[l] = Math.max(lanes[l] ?? 0, LANE_MIN, titleNeed(p));
    });
    if (d.overflow > 0) chip = Math.max(chip, measure.chip(`+${d.overflow}`) + CHIP_EXTRA);
  }
  // Lanes nobody uses on a shared-track day but a later lane does keep a minimal column.
  const filled = Array.from(lanes, (w) => w ?? LANE_MIN);
  const row = rows ? overlay + filled.reduce((a, b) => a + b, 0) + chip : 0;
  const widest = Math.max(single, row);
  return {
    overlay: rows ? overlay : 0,
    lanes: rows ? filled : [],
    chip: rows ? chip : 0,
    width: text ? Math.ceil(widest + SLACK) : widest,
    onlyVertical: !text && widest > 0,
  };
}
