import { daysInMonth, firstDayRow, splitIso } from '../../lib/dates';

/** Weekday rows in the desktop grid: 6 leading empty rows + 31 days. */
export const GRID_ROWS = 37;
/** Number of side-by-side slots in a day cell (left half, right half). */
export const LANE_COUNT = 2;

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
  /** Palette key; opaque to the layout, carried through for rendering. */
  colour?: string;
  /** Draw the title rotated along a multi-day block. */
  labelVertical?: boolean;
}

/** An occurrence placed in a lane of a month column. */
export interface Placed {
  input: LayoutInput;
  lane: number;
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
  /** `lanes[0]` = left half, `lanes[1]` = right half. */
  lanes: (Placed | null)[];
  /** Occurrences that did not fit a lane: shown as "+N". */
  overflow: number;
}

const isMultiDay = (e: LayoutInput) => e.end > e.start;

function spanDays(e: LayoutInput): number {
  const [ys, ms, ds] = splitIso(e.start);
  const [ye, me, de] = splitIso(e.end);
  return Math.round((Date.UTC(ye, me, de) - Date.UTC(ys, ms, ds)) / 86_400_000) + 1;
}

/**
 * Placement order: multi-day first (earlier start, then longer first), then all-day
 * single-day by title, then timed events by start time, then title.
 */
export function compareForLayout(a: LayoutInput, b: LayoutInput): number {
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
 * Lays out one month column. Events are clipped to the month, ordered with
 * {@link compareForLayout} and greedily assigned the first free lane for their whole
 * span, so a multi-day event keeps the same half on every day. Events with no free lane
 * only count towards `overflow` on the days they cover.
 *
 * @returns one entry per day of the month (index = day - 1)
 */
export function layoutMonth(
  inputs: readonly LayoutInput[],
  year: number,
  month: number,
): DayLayout[] {
  const dim = daysInMonth(year, month);
  const first = `${String(year).padStart(4, '0')}-${String(month + 1).padStart(2, '0')}-01`;
  const last = `${first.slice(0, 8)}${String(dim).padStart(2, '0')}`;
  const days: DayLayout[] = Array.from({ length: dim }, (_, i) => ({
    day: i + 1,
    total: 0,
    lanes: Array.from({ length: LANE_COUNT }, () => null),
    overflow: 0,
  }));
  const busy = Array.from({ length: LANE_COUNT }, () => new Uint8Array(dim + 2));

  const visible = inputs.filter((e) => e.start <= last && e.end >= first).sort(compareForLayout);
  for (const input of visible) {
    const s = input.start < first ? 1 : Number(input.start.slice(8, 10));
    const e = input.end > last ? dim : Number(input.end.slice(8, 10));
    let lane = -1;
    for (let l = 0; l < LANE_COUNT && lane < 0; l += 1) {
      const row = busy[l];
      let free = true;
      for (let d = s; d <= e && free; d += 1) if (row?.[d]) free = false;
      if (free) lane = l;
    }
    for (let d = s; d <= e; d += 1) {
      const cell = days[d - 1];
      if (!cell) continue;
      cell.total += 1;
      if (lane < 0) {
        cell.overflow += 1;
      } else {
        const row = busy[lane];
        if (row) row[d] = 1;
        cell.lanes[lane] = { input, lane, showTitle: d === s, joinPrev: d > s, joinNext: d < e };
      }
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
