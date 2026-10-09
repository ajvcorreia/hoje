import { daysInMonth, firstDayRow, splitIso } from '../../lib/dates';
import { DEFAULT_MAX_EVENTS } from '../../lib/maxEvents';

/** Weekday rows in the desktop grid: 6 leading empty rows + 31 days. */
export const GRID_ROWS = 37;

/** What the layout needs to know about one event occurrence. */
export interface LayoutInput {
  /** Unique per occurrence (e.g. `${eventId}:${occurrenceStart}`). */
  key: string;
  /** Inclusive ISO start date. */
  start: string;
  /** Inclusive ISO end date. */
  end: string;
  allDay: boolean;
  /** `HH:mm` (or `HH:mm:ss`) for timed events. */
  startTime?: string | null;
  title: string;
  /** The category glyph drawn before the title of a horizontal event; none when icons are off. */
  icon?: string;
  /** Same, for the title of a vertical (rotated) label; none when icons are off there. */
  verticalIcon?: string;
  /** Palette key; opaque to the layout, carried through for rendering. */
  colour?: string;
  /** Draw the title rotated along a multi-day block. */
  labelVertical?: boolean;
  /**
   * The user's own position among the events of a day (`events.day_order`): 0 = never ordered,
   * 1..n = ordered. Sorts before every other rule, so unordered events keep today's order.
   */
  dayOrder?: number;
}

/** An occurrence placed in a month column. */
export interface Placed {
  input: LayoutInput;
  /** Rotated block: its rotated lane (column). Horizontal event: its packed position that day. */
  lane: number;
  /** Drawn as a rotated label along the block (a narrow column of its own). */
  rotated: boolean;
  /** Days the block covers inside this month column. */
  blockLen: number;
  /** First day of the block inside this month column: draw the title here. */
  showTitle: boolean;
  /** The block also covers the previous day in this column (no border between). */
  joinPrev: boolean;
  /** The block also covers the next day in this column. */
  joinNext: boolean;
}

export interface DayLayout {
  /** 1-based day of month. */
  day: number;
  /** Every occurrence touching this day (placed or not). */
  total: number;
  /**
   * Rotated blocks covering this day by rotated lane (the month has the same number of rotated
   * lanes on every day); `null` where the lane is free on this day.
   */
  rotated: (Placed | null)[];
  /** Visible horizontal events of this day, packed left to right in placement order. */
  items: Placed[];
  /** Occurrences that did not fit: shown as "+N". */
  overflow: number;
}

/** Decides whether an event is drawn as a rotated label along a block of `days` days. */
export type RotatesFn = (input: LayoutInput, days: number) => boolean;

const isMultiDay = (e: LayoutInput) => e.end > e.start;

function spanDays(e: LayoutInput): number {
  const [ys, ms, ds] = splitIso(e.start);
  const [ye, me, de] = splitIso(e.end);
  return Math.round((Date.UTC(ye, me, de) - Date.UTC(ys, ms, ds)) / 86_400_000) + 1;
}

/**
 * Placement order: the user's own order (`dayOrder`, ascending; 0 = never ordered) first, then
 * multi-day first (earlier start, then longer first), then all-day
 * single-day by title, then timed events by start time, then title.
 */
export function compareForLayout(a: LayoutInput, b: LayoutInput): number {
  const oa = a.dayOrder ?? 0;
  const ob = b.dayOrder ?? 0;
  if (oa !== ob) return oa - ob;
  const rank = (e: LayoutInput) => (isMultiDay(e) ? 0 : e.allDay ? 1 : 2);
  const ra = rank(a);
  const rb = rank(b);
  if (ra !== rb) return ra - rb;
  if (ra === 0) {
    if (a.start !== b.start) return a.start < b.start ? -1 : 1;
    const la = spanDays(a);
    const lb = spanDays(b);
    if (la !== lb) return lb - la;
  } else if (ra === 2) {
    const ta = a.startTime ?? '';
    const tb = b.startTime ?? '';
    if (ta !== tb) return ta < tb ? -1 : 1;
  }
  const byTitle = a.title.localeCompare(b.title);
  return byTitle !== 0 ? byTitle : a.key.localeCompare(b.key);
}

/**
 * Lays out one month column. Events are clipped to the month and ordered with
 * {@link compareForLayout}. Rotated blocks (`rotates`: a flagged multi-day event whose name
 * fits) go first, each into the first rotated lane that is free for its whole span, so a block
 * keeps one narrow column on every day and non-overlapping blocks share a column. All other
 * events are then packed per day, left to right, with no gaps. At most `laneCount` events are
 * visible per day in total; the rest only count towards `overflow` on the days they cover.
 *
 * @param laneCount visible events per day (the user's max-events setting)
 * @param rotates which events are drawn rotated; none when omitted
 *
 * @returns one entry per day of the month (index = day - 1)
 */
export function layoutMonth(
  inputs: readonly LayoutInput[],
  year: number,
  month: number,
  laneCount = DEFAULT_MAX_EVENTS,
  rotates?: RotatesFn,
): DayLayout[] {
  const dim = daysInMonth(year, month);
  const first = `${String(year).padStart(4, '0')}-${String(month + 1).padStart(2, '0')}-01`;
  const last = `${first.slice(0, 8)}${String(dim).padStart(2, '0')}`;
  const days: DayLayout[] = Array.from({ length: dim }, (_, i) => ({
    day: i + 1,
    total: 0,
    rotated: [],
    items: [],
    overflow: 0,
  }));
  const shown = new Uint8Array(dim + 2);
  const busy: Uint8Array[] = [];

  const clipped = inputs
    .filter((e) => e.start <= last && e.end >= first)
    .sort(compareForLayout)
    .map((input) => {
      const s = input.start < first ? 1 : Number(input.start.slice(8, 10));
      const e = input.end > last ? dim : Number(input.end.slice(8, 10));
      const len = e - s + 1;
      return { input, s, e, len, rot: len >= 2 && !!rotates?.(input, len) };
    });

  for (const { input, s, e, len } of clipped.filter((c) => c.rot)) {
    let free = true;
    for (let d = s; d <= e && free; d += 1) if ((shown[d] ?? 0) >= laneCount) free = false;
    let lane = -1;
    if (free) {
      for (let l = 0; l < busy.length && lane < 0; l += 1) {
        const row = busy[l] as Uint8Array;
        let ok = true;
        for (let d = s; d <= e && ok; d += 1) if (row[d]) ok = false;
        if (ok) lane = l;
      }
      if (lane < 0) {
        lane = busy.length;
        busy.push(new Uint8Array(dim + 2));
        for (const cell of days) cell.rotated.push(null);
      }
    }
    for (let d = s; d <= e; d += 1) {
      const cell = days[d - 1] as DayLayout;
      cell.total += 1;
      if (lane < 0) {
        cell.overflow += 1;
        continue;
      }
      (busy[lane] as Uint8Array)[d] = 1;
      shown[d] = (shown[d] ?? 0) + 1;
      cell.rotated[lane] = {
        input,
        lane,
        rotated: true,
        blockLen: len,
        showTitle: d === s,
        joinPrev: d > s,
        joinNext: d < e,
      };
    }
  }

  for (const { input, s, e, len } of clipped.filter((c) => !c.rot)) {
    for (let d = s; d <= e; d += 1) {
      const cell = days[d - 1] as DayLayout;
      cell.total += 1;
      if ((shown[d] ?? 0) >= laneCount) {
        cell.overflow += 1;
        continue;
      }
      shown[d] = (shown[d] ?? 0) + 1;
      cell.items.push({
        input,
        lane: cell.items.length,
        rotated: false,
        blockLen: len,
        showTitle: d === s,
        joinPrev: d > s,
        joinNext: d < e,
      });
    }
  }
  return days;
}

/** Row (0-based) holding `day` (1-based) in a column whose day 1 sits on `firstRow`. */
export function rowOfDay(firstRow: number, day: number): number {
  return firstRow + day - 1;
}

/** Rows a month column needs (leading blanks + days), always <= {@link GRID_ROWS}. */
export function rowsUsed(year: number, month: number, weekStart = 1): number {
  return firstDayRow(year, month, weekStart) + daysInMonth(year, month);
}

export type ArrowKey = 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight';

/**
 * Keyboard navigation between day cells. Up/Down move one day inside the month;
 * Left/Right move to the same weekday row in the neighbouring month column (clamped to
 * that month's first/last day). Stays put at the edges of the year.
 */
export function moveFocusDate(iso: string, key: ArrowKey, weekStart = 1): string {
  const [year, month, day] = splitIso(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  const make = (m: number, d: number) => `${String(year).padStart(4, '0')}-${pad(m + 1)}-${pad(d)}`;
  const dim = daysInMonth(year, month);
  switch (key) {
    case 'ArrowUp':
      return make(month, Math.max(1, day - 1));
    case 'ArrowDown':
      return make(month, Math.min(dim, day + 1));
    default: {
      const target = month + (key === 'ArrowLeft' ? -1 : 1);
      if (target < 0 || target > 11) return iso;
      const row = rowOfDay(firstDayRow(year, month, weekStart), day);
      const targetDay = row - firstDayRow(year, target, weekStart) + 1;
      return make(target, Math.min(daysInMonth(year, target), Math.max(1, targetDay)));
    }
  }
}

/** Text of an event drawn horizontally: glyph (if any) then title. */
export function horizontalTitle(input: Pick<LayoutInput, 'title' | 'icon'>): string {
  return input.icon ? `${input.icon} ${input.title}` : input.title;
}

/** Text of a rotated label: glyph (if any) then title. */
export function verticalTitle(input: Pick<LayoutInput, 'title' | 'verticalIcon'>): string {
  return input.verticalIcon ? `${input.verticalIcon} ${input.title}` : input.title;
}
