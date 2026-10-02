import {
  addDays,
  addMonths,
  format,
  getDaysInMonth,
  getISODay,
  isValid,
  parse,
  startOfMonth,
} from 'date-fns';

/**
 * Date helpers. All calendar dates travel as ISO `yyyy-MM-dd` strings (no time zone);
 * they compare correctly as plain strings. Weekdays use ISO numbering (1 = Monday .. 7 = Sunday).
 */

export const ISO_FORMAT = 'yyyy-MM-dd';

/** Formats a Date as `yyyy-MM-dd` in local time. */
export function toIso(date: Date): string {
  return format(date, ISO_FORMAT);
}

/** Parses `yyyy-MM-dd` as a local Date (midnight). Returns null when invalid. */
export function fromIso(iso: string): Date | null {
  const d = parse(iso, ISO_FORMAT, new Date(0));
  return isValid(d) ? d : null;
}

/** Like {@link fromIso} but throws on invalid input; for values the API already validated. */
export function parseIso(iso: string): Date {
  const d = fromIso(iso);
  if (!d) throw new Error(`Invalid ISO date: ${iso}`);
  return d;
}

/** Today as `yyyy-MM-dd`. */
export function todayIso(): string {
  return toIso(new Date());
}

/** ISO weekday (1 = Monday .. 7 = Sunday) of an ISO date. */
export function isoWeekday(iso: string): number {
  return getISODay(parseIso(iso));
}

/** True when the ISO date falls on one of `weekendDays` (ISO weekday numbers). */
export function isWeekend(date: string | Date, weekendDays: readonly number[]): boolean {
  const d = typeof date === 'string' ? parseIso(date) : date;
  return weekendDays.includes(getISODay(d));
}

export function addDaysIso(iso: string, amount: number): string {
  return toIso(addDays(parseIso(iso), amount));
}

export function addMonthsIso(iso: string, amount: number): string {
  return toIso(addMonths(parseIso(iso), amount));
}

/** `yyyy-MM-01` for a (year, 0-based month). */
export function monthStartIso(year: number, month: number): string {
  return toIso(startOfMonth(new Date(year, month, 1)));
}

/** Last day of a (year, 0-based month) as ISO. */
export function monthEndIso(year: number, month: number): string {
  return toIso(new Date(year, month, getDaysInMonth(new Date(year, month, 1))));
}

export function daysInMonth(year: number, month: number): number {
  return getDaysInMonth(new Date(year, month, 1));
}

/**
 * Row (0-based) of day 1 in a weekday-aligned month column.
 * `weekStart` is the ISO weekday of row 0 (1 = Monday).
 */
export function firstDayRow(year: number, month: number, weekStart = 1): number {
  return (getISODay(new Date(year, month, 1)) - weekStart + 7) % 7;
}

/** `[year, month0, day]` from an ISO date without allocating a Date. */
export function splitIso(iso: string): [number, number, number] {
  return [Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))];
}

/**
 * Classic month matrix: weeks of 7 cells, `null` outside the month.
 * Used by the Year view and the mobile month view.
 */
export function monthMatrix(year: number, month: number, weekStart = 1): (string | null)[][] {
  const lead = firstDayRow(year, month, weekStart);
  const total = daysInMonth(year, month);
  const weeks: (string | null)[][] = [];
  let week: (string | null)[] = Array.from({ length: lead }, () => null);
  for (let day = 1; day <= total; day += 1) {
    week.push(toIso(new Date(year, month, day)));
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  }
  if (week.length > 0) {
    while (week.length < 7) week.push(null);
    weeks.push(week);
  }
  return weeks;
}

/** Calendar days covered by an event range, inclusive. */
export function eachDay(startIso: string, endIso: string): string[] {
  const out: string[] = [];
  let d = parseIso(startIso);
  const end = parseIso(endIso);
  while (d <= end) {
    out.push(toIso(d));
    d = addDays(d, 1);
  }
  return out;
}

/** "Thursday 1 January" */
export function formatDayHeading(iso: string): string {
  return format(parseIso(iso), 'EEEE d MMMM');
}

/** "1 Jan 2026" */
export function formatShortDate(iso: string): string {
  return format(parseIso(iso), 'd MMM yyyy');
}

/** "January" */
export function monthName(month: number): string {
  return format(new Date(2000, month, 1), 'MMMM');
}

/** `HH:mm` from an API time (`HH:mm` or `HH:mm:ss`). */
export function shortTime(time: string | null | undefined): string {
  return time ? time.slice(0, 5) : '';
}

/** Letter for an ISO weekday, used in the grid gutter. */
export const WEEKDAY_LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'] as const;
