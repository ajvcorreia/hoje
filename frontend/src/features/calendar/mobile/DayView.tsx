import { format } from 'date-fns';
import type { Occurrence } from '../../../api/types';
import { parseIso } from '../../../lib/dates';
import { categoryMap, useCategories } from '../../categories/api';
import { useCategoryIcon, withIcon } from '../../categories/icons';
import { QuickAdd } from '../../events/QuickAdd';
import { ReminderBell } from '../../events/ReminderBell';
import { formatTimeRange, occurrenceKey } from '../../events/occurrences';
import type { HolidayDay } from '../../holidays/api';
import { HolidayCards } from '../../holidays/HolidayList';
import { dayOfLabel } from './mobileLib';

interface DayViewProps {
  date: string;
  /** The day's visible occurrences, all-day first then by start time. */
  occurrences: Occurrence[];
  loading: boolean;
  /** The day's holidays, shown as non-interactive cards above the events. */
  holidays?: HolidayDay[];
  onSelectEvent(eventId: string): void;
}

/** The selected day's heading and its events as stacked cards. */
export function DayView({ date, occurrences, loading, holidays, onSelectEvent }: DayViewProps) {
  const { data: categories } = useCategories();
  const byId = categoryMap(categories);
  const iconOf = useCategoryIcon();
  return (
    <div className="space-y-3">
      <h2 className="text-base font-semibold">{format(parseIso(date), 'EEEE, d MMMM')}</h2>
      <HolidayCards holidays={holidays} />
      {occurrences.length === 0 ? (
        <p className="text-sm text-text-muted">{loading ? 'Loading…' : 'No events'}</p>
      ) : (
        <ul aria-label={`Events on ${date}`} className="space-y-2">
          {occurrences.map((o) => {
            const category = byId.get(o.event.category_id);
            const time = formatTimeRange(o.event);
            const dayOf = dayOfLabel(o, date);
            return (
              <li key={occurrenceKey(o)}>
                <button
                  type="button"
                  data-cat={category?.colour ?? 'slate'}
                  onClick={() => onSelectEvent(o.event_id)}
                  className="m-card flex min-h-14 w-full flex-col items-start justify-center rounded-md px-3 py-2 text-left"
                >
                  <span className="flex w-full items-start gap-1.5">
                    <span className="min-w-0 flex-1 break-words text-sm font-medium">
                      {withIcon(iconOf(o.event.category_id), o.event.title)}
                    </span>
                    <ReminderBell event={o.event} />
                  </span>
                  <span className="w-full break-words text-xs text-text-muted">
                    {[category?.name, time || (o.event.all_day ? 'All day' : ''), dayOf]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <QuickAdd date={date} inputId={`m-quick-add-${date}`} />
    </div>
  );
}
