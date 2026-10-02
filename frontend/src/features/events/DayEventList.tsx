import type { Occurrence } from '../../api/types';
import { categoryMap, useCategories } from '../categories/api';
import { CategorySwatch } from '../categories/CategorySwatch';
import { formatTimeRange } from './occurrences';

interface DayEventListProps {
  /** ISO date the list is for (used for the accessible name). */
  date: string;
  /** That day's occurrences, already filtered and sorted. */
  occurrences: Occurrence[];
  /** Called with the event id when a row is chosen (open the editor). */
  onSelect(eventId: string): void;
}

/**
 * The events of one day: colour swatch, title, category name and time (when timed).
 * The category name is always written out so colour is never the only signal.
 * Used by the desktop day popover and the mobile day view.
 */
export function DayEventList({ date, occurrences, onSelect }: DayEventListProps) {
  const { data: categories } = useCategories();
  const byId = categoryMap(categories);
  if (occurrences.length === 0) {
    return <p className="py-1 text-sm text-text-muted">No events</p>;
  }
  return (
    <ul aria-label={`Events on ${date}`} className="space-y-0.5">
      {occurrences.map((o) => {
        const category = byId.get(o.event.category_id);
        const time = formatTimeRange(o.event);
        return (
          <li key={`${o.event_id}:${o.occurrence_start}`}>
            <button
              type="button"
              onClick={() => onSelect(o.event_id)}
              className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-surface-muted md:min-h-9"
            >
              <CategorySwatch colour={category?.colour} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{o.event.title}</span>
                <span className="block truncate text-xs text-text-muted">
                  {[category?.name, time].filter(Boolean).join(' · ')}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
