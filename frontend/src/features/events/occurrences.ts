import type { Category, Occurrence } from '../../api/types';
import { eachDay, shortTime } from '../../lib/dates';
import type { LayoutInput } from '../calendar/layout';

/** Stable key of one occurrence (a repeating event has one per repeat). */
export const occurrenceKey = (o: Occurrence) => `${o.event_id}:${o.occurrence_start}`;

/** Drops occurrences whose category is hidden by the filter chips. */
export function filterVisible(
  occurrences: readonly Occurrence[] | undefined,
  categories: readonly Category[] | undefined,
): Occurrence[] {
  if (!occurrences) return [];
  const hidden = new Set((categories ?? []).filter((c) => c.hidden).map((c) => c.id));
  return hidden.size === 0
    ? [...occurrences]
    : occurrences.filter((o) => !hidden.has(o.event.category_id));
}

/** The user's own order (`day_order`, 0 = never ordered) first, then all-day, start time, title. */
export function compareWithinDay(a: Occurrence, b: Occurrence): number {
  const oa = a.event.day_order ?? 0;
  const ob = b.event.day_order ?? 0;
  if (oa !== ob) return oa - ob;
  if (a.event.all_day !== b.event.all_day) return a.event.all_day ? -1 : 1;
  const ta = a.event.start_time ?? '';
  const tb = b.event.start_time ?? '';
  if (ta !== tb) return ta < tb ? -1 : 1;
  return a.event.title.localeCompare(b.event.title);
}

/**
 * Buckets occurrences by every day they cover inside `[from, to]` (inclusive ISO dates),
 * each bucket sorted with {@link compareWithinDay}.
 */
export function groupByDay(
  occurrences: readonly Occurrence[],
  from: string,
  to: string,
): Map<string, Occurrence[]> {
  const map = new Map<string, Occurrence[]>();
  for (const o of occurrences) {
    const start = o.occurrence_start < from ? from : o.occurrence_start;
    const end = o.occurrence_end > to ? to : o.occurrence_end;
    if (start > end) continue;
    for (const day of eachDay(start, end)) {
      const bucket = map.get(day);
      if (bucket) bucket.push(o);
      else map.set(day, [o]);
    }
  }
  for (const bucket of map.values()) bucket.sort(compareWithinDay);
  return map;
}

/** Adapter from API occurrences to the grid layout input. */
export function toLayoutInput(o: Occurrence, colour?: string): LayoutInput {
  return {
    key: occurrenceKey(o),
    start: o.occurrence_start,
    end: o.occurrence_end,
    allDay: o.event.all_day,
    startTime: o.event.start_time,
    title: o.event.title,
    colour,
    labelVertical: o.event.label_vertical,
    dayOrder: o.event.day_order ?? 0,
  };
}

/** "09:30" or "09:30–10:15" for timed events; empty for all-day ones. */
export function formatTimeRange(
  event: Pick<Occurrence['event'], 'all_day' | 'start_time' | 'end_time'>,
): string {
  if (event.all_day || !event.start_time) return '';
  const start = shortTime(event.start_time);
  const end = shortTime(event.end_time);
  return end ? `${start}–${end}` : start;
}
