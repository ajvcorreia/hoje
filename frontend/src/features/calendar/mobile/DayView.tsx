import { format } from 'date-fns';
import type { Occurrence } from '../../../api/types';
import { parseIso } from '../../../lib/dates';
import { categoryMap, useCategories } from '../../categories/api';
import { QuickAdd } from '../../events/QuickAdd';
import { formatTimeRange, occurrenceKey } from '../../events/occurrences';
import { dayOfLabel } from './mobileLib';

interface DayViewProps {
  date: string;
  /** The day's visible occurrences, all-day first then by start time. */
  occurrences: Occurrence[];
  loading: boolean;
  onSelectEvent(eventId: string): void;
}

/** The selected day's heading and its events as stacked cards. */
export function DayView({ date, occurrences, loading, onSelectEvent }: DayViewProps) {
  const { data: categories } = useCategories();
  const byId = categoryMap(categories);
  return (
    <div className="space-y-3">
      <h2 className="text-base font-semibold">{format(parseIso(date), 'EEEE, d MMMM')}</h2>
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
                  <span className="w-full break-words text-sm font-medium">{o.event.title}</span>
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
