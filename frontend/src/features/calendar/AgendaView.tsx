import { useMemo, useState } from 'react';
import { format } from 'date-fns';
import type { Occurrence } from '../../api/types';
import { describeError } from '../../lib/errors';
import { addMonthsIso, formatShortDate, parseIso } from '../../lib/dates';
import { btnSecondary } from '../../components/ui/classes';
import { categoryMap, useCategories } from '../categories/api';
import { CategorySwatch } from '../categories/CategorySwatch';
import { useCategoryIcon } from '../categories/icons';
import { useOccurrences } from '../events/api';
import { compareWithinDay, filterVisible, formatTimeRange } from '../events/occurrences';
import { ReminderBell } from '../events/ReminderBell';
import { useBirthdaysBetween } from '../birthdays/api';
import { CAKE, birthdayName, type HolidayDay } from '../holidays/api';

interface AgendaViewProps {
  today: string;
  onSelectEvent(eventId: string): void;
}

const STEP_MONTHS = 3;

interface DayGroup {
  date: string;
  items: Occurrence[];
  /** Synced birthdays of that day (read-only), listed before the events. */
  birthdays: HolidayDay[];
}

/**
 * Groups occurrences under their first day on or after `today`, in date order, and adds the
 * birthdays of each day (a day with only birthdays gets a group too).
 */
function groupForAgenda(
  occurrences: Occurrence[],
  today: string,
  birthdays: ReadonlyMap<string, HolidayDay[]>,
): DayGroup[] {
  const map = new Map<string, Occurrence[]>();
  for (const o of occurrences) {
    const day = o.occurrence_start < today ? today : o.occurrence_start;
    const bucket = map.get(day);
    if (bucket) bucket.push(o);
    else map.set(day, [o]);
  }
  for (const date of birthdays.keys()) if (!map.has(date)) map.set(date, []);
  return [...map.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([date, items]) => ({
      date,
      items: items.sort(compareWithinDay),
      birthdays: birthdays.get(date) ?? [],
    }));
}

/**
 * Chronological list from today forward, grouped by month and day. It loads three months
 * at a time; "Load more" extends the horizon. Category names are always written out.
 */
export function AgendaView({ today, onSelectEvent }: AgendaViewProps) {
  const [months, setMonths] = useState(STEP_MONTHS);
  const to = addMonthsIso(today, months);
  const { data, isPending, isError, error } = useOccurrences(today, to);
  const { data: categories } = useCategories();
  const byId = categoryMap(categories);
  const iconOf = useCategoryIcon();
  const birthdays = useBirthdaysBetween(today, to);
  const groups = useMemo(
    () => groupForAgenda(filterVisible(data, categories), today, birthdays),
    [data, categories, today, birthdays],
  );

  if (isPending) return <p className="py-4 text-sm text-text-muted">Loading...</p>;
  if (isError) {
    return (
      <p role="alert" className="py-4 text-sm text-danger">
        {describeError(error)}
      </p>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl pb-6">
        {groups.length === 0 ? (
          <p className="py-4 text-sm text-text-muted">
            Nothing planned until {formatShortDate(to)}.
          </p>
        ) : null}
        {groups.map((group, index) => {
          const showMonth = group.date.slice(0, 7) !== groups[index - 1]?.date.slice(0, 7);
          const date = parseIso(group.date);
          return (
            <div key={group.date}>
              {showMonth ? (
                <h2 className="sticky top-0 border-b border-border bg-bg py-2 text-sm font-semibold">
                  {format(date, 'MMMM yyyy')}
                </h2>
              ) : null}
              <div className="flex gap-4 border-b border-border py-2">
                <div className="w-14 shrink-0 text-sm">
                  <div className="font-medium">{format(date, 'EEE d')}</div>
                  {group.date === today ? <div className="text-xs text-accent">Today</div> : null}
                </div>
                <ul className="min-w-0 flex-1 space-y-0.5">
                  {group.birthdays.map((b) => (
                    <li
                      key={b.id}
                      className="flex min-h-9 items-center gap-2 rounded-md px-2 py-1 text-sm"
                    >
                      <span aria-hidden="true">{CAKE}</span>
                      <span className="min-w-0 flex-1 break-words">{birthdayName(b)}</span>
                      <span className="shrink-0 text-xs text-text-muted">Birthday</span>
                    </li>
                  ))}
                  {group.items.map((o) => {
                    const category = byId.get(o.event.category_id);
                    const time = formatTimeRange(o.event);
                    const until =
                      o.occurrence_end > o.occurrence_start
                        ? `until ${format(parseIso(o.occurrence_end), 'd MMM')}`
                        : '';
                    return (
                      <li key={`${o.event_id}:${o.occurrence_start}`}>
                        <button
                          type="button"
                          onClick={() => onSelectEvent(o.event_id)}
                          className="flex min-h-9 w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-surface-muted"
                        >
                          <CategorySwatch colour={category?.colour} icon={iconOf(category?.id)} />
                          <span className="min-w-0 flex-1 break-words font-medium">
                            {o.event.title}
                          </span>
                          <ReminderBell event={o.event} />
                          <span className="max-w-[45%] shrink-0 break-words text-right text-xs text-text-muted">
                            {[category?.name, time, until].filter(Boolean).join(' · ')}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          );
        })}
        <div className="pt-4 text-center">
          <button
            type="button"
            className={btnSecondary}
            onClick={() => setMonths((m) => m + STEP_MONTHS)}
          >
            Load more
          </button>
        </div>
      </div>
    </div>
  );
}
