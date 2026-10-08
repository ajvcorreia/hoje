import type { DayLayout, RotatesFn } from './layout';

/** Horizontal padding of an event / holiday box (`padding: 0 4px`). */
const BOX_PADDING = 8;
/** Right border of a lane's box (`.cal-ev` in a shared track): it eats into the track's width. */
const LANE_BORDER = 1;
/** Sub-pixel rounding: never let a title land exactly on the edge. */
const SLACK = 4;
/** The "+N" chip: 4px padding each side, 1px border each side, 2px from the cell edge. */
const CHIP_EXTRA = 12;
/** A lane column is never narrower than this, so even a block without a title stays visible. */
const LANE_MIN = 12;

/** Smallest font size of a rotated label, in rem (keep in sync with `.cal-vlabel-text`). */
export const VLABEL_MIN_REM = 0.5625;
/** Line height of rotated text (`.cal-vlabel-text`), as a multiple of its font size. */
const VLABEL_LINE_HEIGHT = 1.15;
/** The user's preferred rotated font size (px, at a 16px root) when none is given. */
export const DEFAULT_VERTICAL_SIZE = 12;
/** Height a rotated label cannot use: 2 x 2px block padding, the 6px CSS margin and 2px slack. */
const VLABEL_RESERVED = 12;
/** Safety factor on the measured length of a rotated name (hinting, vertical glyph advances). */
const VLABEL_SAFETY = 1.03;
/** Row height used until the grid has measured its container. */
export const DEFAULT_ROW_HEIGHT = 16;

/** Fonts the grid draws event text with, as canvas `font` strings. */
export interface FitFonts {
  normal: string;
  italic: string;
  chip: string;
  /** Root font size in px: rotated labels size themselves in rem. */
  rem: number;
  /** The cell's font family, for the bold rotated labels. */
  family: string;
}

/** Used until the grid has read the real cell font. */
export const DEFAULT_FIT_FONTS: FitFonts = {
  normal: '400 11px sans-serif',
  italic: 'italic 400 11px sans-serif',
  chip: '400 9px sans-serif',
  rem: 16,
  family: 'sans-serif',
};

export interface TextMeasurer {
  text(value: string): number;
  italic(value: string): number;
  chip(value: string): number;
  /** Width in px of one single-line rotated label column at the preferred size. */
  lane: number;
  /**
   * How `title` is drawn rotated along a block of `days` rows (lines, size, column width), or
   * `null` when it cannot fit even wrapped at the minimum size (it is then a horizontal title).
   */
  plan(title: string, days: number): VerticalPlan | null;
}

/** How one rotated label is set: wrapped lines, the font size they use and the column they need. */
export interface VerticalPlan {
  /** 1..3 lines in reading order (each is drawn as its own column, centred). */
  lines: string[];
  /** Effective font size in px (the preferred size unless the name had to shrink). */
  size: number;
  /** Width in px of the lane column the label needs. */
  width: number;
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

/** Forget cached widths (they were measured with a font that has since been replaced). */
export function clearMeasureCache(): void {
  widths.clear();
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

/**
 * Length of a vertical label's bold `title` in em, i.e. its length in px at a 1px font size.
 * CSS divides the block height by this to shrink long names until they fit.
 */
export function verticalLabelEm(title: string, family = 'sans-serif'): number {
  const em = measureText(title, `700 100px ${family}`) / 100;
  return Math.max(0.5, em + VLABEL_TRACKING * title.length);
}

/** A rotated name is wrapped into at most this many lines. */
export const VLABEL_MAX_LINES = 3;

/**
 * Width in px of one rotated label column for a preferred font size of `size` px (at a 16px root;
 * it scales with the root font size like the rem it replaces): one line height plus 2px.
 * `lines` columns of text side by side need that many line heights.
 */
export function verticalLaneWidth(size: number, rem = 16, lines = 1): number {
  return Math.ceil(VLABEL_LINE_HEIGHT * size * (rem / 16) * lines) + 2;
}

/** Best split of `words` into `k` contiguous lines: shortest longest line, then most even. */
function balancedLines(words: string[], k: number, em: (line: string) => number): string[] {
  const n = words.length;
  let best: string[] = [words.join(' ')];
  let bestMax = Infinity;
  let bestSq = Infinity;
  const consider = (cuts: number[]) => {
    const lines: string[] = [];
    let prev = 0;
    for (const c of [...cuts, n]) {
      lines.push(words.slice(prev, c).join(' '));
      prev = c;
    }
    const lens = lines.map(em);
    const max = Math.max(...lens);
    const sq = lens.reduce((a, l) => a + l * l, 0);
    if (max < bestMax - 1e-9 || (Math.abs(max - bestMax) <= 1e-9 && sq < bestSq)) {
      best = lines;
      bestMax = max;
      bestSq = sq;
    }
  };
  if (k === 1) consider([]);
  else if (k === 2) for (let a = 1; a < n; a += 1) consider([a]);
  else for (let a = 1; a < n - 1; a += 1) for (let b = a + 1; b < n; b += 1) consider([a, b]);
  return best;
}

/**
 * How a rotated label of `days` rows of `rowHeight` px sets `title`, or `null` when it cannot fit.
 * In order: one line at the preferred `size` (px at a 16px root); else the fewest lines (2..3,
 * wrapped at spaces, greedy) whose longest line fits at that size; else three lines at the most
 * even split, shrunk until the longest line fits, down to the 9px minimum; else `null` and the
 * event is drawn as a horizontal title. A word is never broken, so a single long word that does
 * not fit even at the minimum size is the `null` case; a name is never ellipsized or cut.
 */
export function verticalPlan(
  title: string,
  days: number,
  rowHeight: number,
  fonts: Pick<FitFonts, 'rem' | 'family'>,
  size = DEFAULT_VERTICAL_SIZE,
): VerticalPlan | null {
  const words = title.split(/\s+/).filter(Boolean);
  if (words.length === 0) return null;
  const em = (line: string) => verticalLabelEm(line, fonts.family) * VLABEL_SAFETY;
  const height = days * rowHeight - VLABEL_RESERVED;
  const preferred = size * (fonts.rem / 16);
  const floor = Math.min(VLABEL_MIN_REM * fonts.rem, preferred);
  const plan = (lines: string[], px: number): VerticalPlan => ({
    lines,
    size: px,
    width: verticalLaneWidth(px, 16, lines.length),
  });

  const whole = words.join(' ');
  if (em(whole) * preferred <= height) return plan([whole], preferred);

  // Greedy: the fewest lines that fit the height at the preferred size.
  const limit = height / preferred;
  const greedy: string[] = [];
  let current = '';
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (!current || em(next) <= limit) {
      current = next;
    } else {
      greedy.push(current);
      current = word;
    }
  }
  greedy.push(current);
  if (greedy.length <= VLABEL_MAX_LINES && greedy.every((l) => em(l) <= limit)) {
    return plan(greedy, preferred);
  }

  // Most even wrap into up to three lines, shrunk until its longest line fits.
  const lines = balancedLines(words, Math.min(VLABEL_MAX_LINES, words.length), em);
  const shrunk = Math.min(preferred, height / Math.max(...lines.map(em)));
  if (shrunk < floor) return null;
  return plan(lines, Math.floor(shrunk * 100) / 100);
}

export function measurerFor(
  fonts: FitFonts,
  rowHeight = DEFAULT_ROW_HEIGHT,
  verticalSize = DEFAULT_VERTICAL_SIZE,
): TextMeasurer {
  const plans = new Map<string, VerticalPlan | null>();
  return {
    text: (value) => measureText(value, fonts.normal),
    italic: (value) => measureText(value, fonts.italic),
    chip: (value) => measureText(value, fonts.chip),
    lane: verticalLaneWidth(verticalSize, fonts.rem),
    plan: (title, days) => {
      const key = `${days}\u0000${title}`;
      if (!plans.has(key))
        plans.set(key, verticalPlan(title, days, rowHeight, fonts, verticalSize));
      return plans.get(key) ?? null;
    },
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
    // The cell is 0.6875rem.
    rem: (size * 16) / 11,
    family,
  };
}

/**
 * The rule that decides which events are drawn as a rotated label: flagged as vertical, a block
 * of 2+ days of the month and a name that fits the block height at the minimum size. It does not
 * depend on lanes, so it can run before lane assignment.
 */
export function rotationRule(measure: TextMeasurer): RotatesFn {
  return (input, days) =>
    !!input.labelVertical && days >= 2 && measure.plan(input.title, days) !== null;
}

/** Track widths (px) of one day cell's event area (everything right of the day number). */
export interface DayTracks {
  /** Rotated columns, 0..h where h is the highest rotated lane covering the day. */
  rotated: number;
  /** Total width (px) of those rotated columns. */
  rotatedWidth: number;
  /** Holiday / birthday track, after the rotated columns; 0 when the day has none. */
  overlay: number;
  /** Minimum width of each horizontal event, in packed order. */
  items: number[];
  /** "+N" chip track, last; 0 when the day does not overflow. */
  chip: number;
  /** Minimum width of the whole event area, slack included. */
  need: number;
  /** The day shows horizontal text (overlay or a title): it gets {@link SLACK}. */
  text: boolean;
  /** The day has horizontal content (overlay or events), not just rotated columns. */
  horizontal: boolean;
}

/**
 * The tracks of one day: rotated columns at a fixed width, then the overlay text, then one track
 * per horizontal event in packed order and the "+N" chip. Nothing is shared with other days: a
 * rotated label keeps its x offset because its column index is its lane.
 */
export function dayTracks(
  d: DayLayout,
  name: string | undefined,
  measure: TextMeasurer,
  lanes: readonly number[] = [],
): DayTracks {
  let rotatedCols = 0;
  d.rotated.forEach((p, l) => {
    if (p) rotatedCols = l + 1;
  });
  let rotatedWidth = 0;
  for (let l = 0; l < rotatedCols; l += 1) rotatedWidth += lanes[l] ?? measure.lane;
  const overlay = name ? measure.italic(name) + BOX_PADDING : 0;
  const items = d.items.map((p) =>
    p.showTitle ? measure.text(p.input.title) + BOX_PADDING + LANE_BORDER : LANE_MIN,
  );
  const chip = d.overflow > 0 ? measure.chip(`+${d.overflow}`) + CHIP_EXTRA : 0;
  const text = overlay > 0 || d.items.some((p) => p.showTitle);
  const sum = rotatedWidth + overlay + items.reduce((a, b) => a + b, 0) + chip;
  return {
    rotated: rotatedCols,
    rotatedWidth,
    overlay,
    items,
    chip,
    need: text ? Math.ceil(sum + SLACK) : sum,
    text,
    horizontal: overlay > 0 || items.length > 0 || chip > 0,
  };
}

/** The geometry of one month column. */
export interface MonthTracks {
  /** One entry per day (index = day - 1). */
  days: DayTracks[];
  /** Width (px) of a single-line rotated column at the preferred size. */
  lane: number;
  /** Width (px) of each rotated lane: the widest label (lines x size) the lane holds this month. */
  lanes: number[];
  /** How each rotated label is set, by `${input.key}:${first day}` (see MonthColumn). */
  labels: Record<string, VerticalPlan>;
  /** Minimum width of the event area: the widest day. */
  width: number;
  /** Nothing but rotated labels: the month needs no horizontal-text minimum. */
  onlyVertical: boolean;
}

/**
 * Widths one month column needs so that nothing is cut off: the widest day, where a day needs its
 * rotated columns, overlay text, event titles and chip side by side. A rotated label needs one
 * line height, not its text width; a flagged block whose name does not fit its height is a
 * horizontal title like any other (see {@link rotationRule}).
 *
 * @param layout the month laid out with {@link rotationRule}
 * @param overlays holiday / birthday text by 1-based day of month
 */
export function monthTracks(
  layout: readonly DayLayout[],
  overlays: ReadonlyMap<number, string>,
  measure: TextMeasurer,
): MonthTracks {
  const lanes: number[] = (layout[0]?.rotated ?? []).map(() => 0);
  const labels: Record<string, VerticalPlan> = {};
  for (const d of layout) {
    for (const p of d.rotated) {
      if (!p?.showTitle) continue;
      const plan = measure.plan(p.input.title, p.blockLen);
      if (plan) labels[`${p.input.key}:${d.day}`] = plan;
      lanes[p.lane] = Math.max(lanes[p.lane] ?? 0, plan?.width ?? measure.lane);
    }
  }
  const days = layout.map((d) => dayTracks(d, overlays.get(d.day), measure, lanes));
  const width = days.reduce((m, t) => Math.max(m, t.need), 0);
  return {
    days,
    lane: measure.lane,
    lanes,
    labels,
    width,
    onlyVertical: width > 0 && days.every((t) => !t.horizontal),
  };
}
