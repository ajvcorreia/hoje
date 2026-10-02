import { format } from 'date-fns';
import type { Occurrence } from '../../../api/types';
import { WEEKDAY_LETTERS, isWeekend, monthMatrix, parseIso, splitIso } from '../../../lib/dates';
import { categoryMap, useCategories } from '../../categories/api';
import { DayEventList } from '../../events/DayEventList';
import { occurrenceKey } from '../../events/occurrences';
import { QuickAdd } from '../../events/QuickAdd';

interface MonthViewProps {
  selected: string;
  today: string;
  weekendDays: readonly number[];
  byDay: ReadonlyMap<string, Occurrence[]>;
  onSelect(date: string): void;
  onSelectEvent(eventId: string): void;
}

const MAX_DOTS = 3;

/** Classic Monday-first month grid with up to three category dots per date. */
export function MonthView({
  selected,
  today,
  weekendDays,
  byDay,
  onSelect,
  onSelectEvent,
}: MonthViewProps) {
  const { data: categories } = useCategories();
  const byId = categoryMap(categories);
  const [year, month] = splitIso(selected);
  const weeks = monthMatrix(year, month);
  const selectedEvents = byDay.get(selected) ?? [];
  return (
    <div className="space-y-3">
      <div role="grid" aria-label={format(new Date(year, month, 1), 'MMMM yyyy')}>
        <div role="row" className="grid grid-cols-7 text-center text-xs text-text-muted">
          {WEEKDAY_LETTERS.map((letter, i) => (
            <span key={i} role="columnheader" aria-label={format(new Date(2024, 0, 1 + i), 'EEEE')}>
              {letter}
            </span>
          ))}
        </div>
        {weeks.map((week, w) => (
          <div key={w} role="row" className="grid grid-cols-7">
            {week.map((day, c) =>
              day === null ? (
                <span key={c} role="gridcell" className="min-h-12" />
              ) : (
                <MonthCell
                  key={day}
                  day={day}
                  occurrences={byDay.get(day) ?? []}
                  colourOf={(o) => byId.get(o.event.category_id)?.colour ?? 'slate'}
                  selected={day === selected}
                  today={day === today}
                  weekend={isWeekend(day, weekendDays)}
                  onSelect={onSelect}
                />
              ),
            )}
          </div>
        ))}
      </div>
      <h2 className="text-base font-semibold">{format(parseIso(selected), 'EEEE, d MMMM')}</h2>
      <DayEventList date={selected} occurrences={selectedEvents} onSelect={onSelectEvent} />
      <QuickAdd date={selected} inputId={`m-quick-add-${selected}`} />
    </div>
  );
}

interface MonthCellProps {
  day: string;
  occurrences: Occurrence[];
  colourOf(o: Occurrence): string;
  selected: boolean;
  today: boolean;
  weekend: boolean;
  onSelect(date: string): void;
}

function MonthCell({
  day,
  occurrences,
  colourOf,
  selected,
  today,
  weekend,
  onSelect,
}: MonthCellProps) {
  const count = occurrences.length;
  return (
    <span role="gridcell" className="min-w-0">
      <button
        type="button"
        data-date={day}
        aria-label={`${format(parseIso(day), 'EEEE d MMMM')}, ${count} ${count === 1 ? 'event' : 'events'}`}
        aria-current={today ? 'date' : undefined}
        aria-pressed={selected}
        onClick={() => onSelect(day)}
        className={`flex min-h-12 w-full flex-col items-center justify-center gap-0.5 rounded-md border text-sm tabular-nums ${
          selected
            ? 'border-accent bg-accent text-accent-contrast'
            : today
              ? 'border-accent bg-today'
              : weekend
                ? 'border-transparent bg-weekend'
                : 'border-transparent'
        }`}
      >
        <span aria-hidden="true">{Number(day.slice(8, 10))}</span>
        <span aria-hidden="true" className="flex h-1.5 items-center gap-0.5">
          {occurrences.slice(0, MAX_DOTS).map((o) => (
            <span key={occurrenceKey(o)} data-cat={colourOf(o)} className="m-dot" />
          ))}
        </span>
      </button>
    </span>
  );
}
