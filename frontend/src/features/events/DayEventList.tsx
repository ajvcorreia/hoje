import { useEffect, useRef } from 'react';
import type { Occurrence } from '../../api/types';
import { categoryMap, useCategories } from '../categories/api';
import { CategorySwatch } from '../categories/CategorySwatch';
import { formatTimeRange } from './occurrences';
import { ReminderBell } from './ReminderBell';

interface DayEventListProps {
  /** ISO date the list is for (used for the accessible name). */
  date: string;
  /** That day's occurrences, already filtered and sorted. */
  occurrences: Occurrence[];
  /** Called with the event id when a row is chosen (open the editor). */
  onSelect(eventId: string): void;
  /**
   * Called with the event ids in their new order after a move. When given and more than one
   * event is listed, every row gets Move up / Move down buttons and a hint is shown.
   */
  onReorder?(eventIds: string[]): void;
}

function Chevron({ down }: { down?: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={down ? 'M6 9l6 6 6-6' : 'M6 15l6-6 6 6'} />
    </svg>
  );
}

const MOVE_BUTTON =
  'inline-flex min-h-8 min-w-8 items-center justify-center rounded-md text-text-muted hover:bg-surface-muted hover:text-text disabled:opacity-30 disabled:hover:bg-transparent';

/**
 * The events of one day: colour swatch, title, category name and time (when timed).
 * The category name is always written out so colour is never the only signal.
 * Used by the desktop day popover and the mobile day view. With `onReorder` the rows can be
 * moved up and down; names are never truncated.
 */
export function DayEventList({ date, occurrences, onSelect, onReorder }: DayEventListProps) {
  const { data: categories } = useCategories();
  const byId = categoryMap(categories);
  const listRef = useRef<HTMLUListElement>(null);
  // The row that was just moved keeps keyboard focus on its button (or the other one at an end).
  const refocus = useRef<{ id: string; dir: 'up' | 'down' } | null>(null);
  useEffect(() => {
    const target = refocus.current;
    if (!target) return;
    refocus.current = null;
    const find = (dir: string) =>
      listRef.current?.querySelector<HTMLButtonElement>(
        `button[data-move="${dir}"][data-event-id="${target.id}"]:not([disabled])`,
      );
    (find(target.dir) ?? find(target.dir === 'up' ? 'down' : 'up'))?.focus();
  }, [occurrences]);

  if (occurrences.length === 0) {
    return <p className="py-1 text-sm text-text-muted">No events</p>;
  }
  const reorderable = onReorder !== undefined && occurrences.length > 1;
  const move = (index: number, dir: 'up' | 'down') => {
    const ids = occurrences.map((o) => o.event_id);
    const to = dir === 'up' ? index - 1 : index + 1;
    const moved = ids[index];
    const other = ids[to];
    if (moved === undefined || other === undefined) return;
    ids[index] = other;
    ids[to] = moved;
    refocus.current = { id: moved, dir };
    onReorder?.(ids);
  };
  return (
    <>
      <ul ref={listRef} aria-label={`Events on ${date}`} className="space-y-0.5">
        {occurrences.map((o, index) => {
          const category = byId.get(o.event.category_id);
          const time = formatTimeRange(o.event);
          return (
            <li key={`${o.event_id}:${o.occurrence_start}`} className="flex items-center gap-0.5">
              <button
                type="button"
                onClick={() => onSelect(o.event_id)}
                className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-surface-muted md:min-h-9"
              >
                <CategorySwatch colour={category?.colour} />
                <span className="min-w-0 flex-1">
                  <span className="block break-words font-medium">{o.event.title}</span>
                  <span className="block break-words text-xs text-text-muted">
                    {[category?.name, time].filter(Boolean).join(' · ')}
                  </span>
                </span>
                <ReminderBell event={o.event} />
              </button>
              {reorderable && (
                <span className="flex shrink-0 flex-col">
                  <button
                    type="button"
                    data-move="up"
                    data-event-id={o.event_id}
                    aria-label={`Move ${o.event.title} up`}
                    disabled={index === 0}
                    onClick={() => move(index, 'up')}
                    className={MOVE_BUTTON}
                  >
                    <Chevron />
                  </button>
                  <button
                    type="button"
                    data-move="down"
                    data-event-id={o.event_id}
                    aria-label={`Move ${o.event.title} down`}
                    disabled={index === occurrences.length - 1}
                    onClick={() => move(index, 'down')}
                    className={MOVE_BUTTON}
                  >
                    <Chevron down />
                  </button>
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {reorderable && (
        <p className="mt-1 text-xs text-text-muted">
          Order is shared by all days of a multi-day event. Vertical labels of multi-day events
          always come first in the month grid.
        </p>
      )}
    </>
  );
}
