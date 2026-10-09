import type { Occurrence } from '../../api/types';

const compactFormat = new Intl.NumberFormat('en', {
  notation: 'compact',
  maximumFractionDigits: 1,
});
export const fullFormat = new Intl.NumberFormat('en');

/** Visible count: plain below 1000, compact ("1.2K") above, so the pill stays narrow. */
export const formatCount = (n: number) => (n >= 1000 ? compactFormat.format(n) : String(n));

/**
 * Event OCCURRENCES per category id (a repeating event counts once per repeat) among the
 * given occurrences, i.e. the range the calendar currently shows. Callers pass the list NOT
 * filtered by hidden categories, so a pill that is toggled off still shows how many events it
 * would reveal.
 */
export function countByCategory(
  occurrences: readonly Occurrence[] | undefined,
): ReadonlyMap<string, number> {
  const counts = new Map<string, number>();
  for (const o of occurrences ?? []) {
    counts.set(o.event.category_id, (counts.get(o.event.category_id) ?? 0) + 1);
  }
  return counts;
}
