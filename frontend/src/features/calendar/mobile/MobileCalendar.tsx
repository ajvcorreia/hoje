import { useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { useEffect, useMemo, useState } from 'react';
import { useAuthState } from '../../../app/useAuthState';
import { btnSecondary } from '../../../components/ui/classes';
import { addDaysIso, addMonthsIso, parseIso, todayIso } from '../../../lib/dates';
import { describeError } from '../../../lib/errors';
import { useCategories } from '../../categories/api';
import { CategoryChips } from '../../categories/CategoryChips';
import { occurrencesQuery, useOccurrences } from '../../events/api';
import { EventEditor } from '../../events/EventEditor';
import { filterVisible, groupByDay } from '../../events/occurrences';
import { DayView } from './DayView';
import {
  dayRange,
  loadView,
  monthRange,
  saveView,
  useSwipe,
  type MobileView,
} from './mobileLib';
import { MonthView } from './MonthView';
import { QuickAddSheet } from './QuickAddSheet';
import { WeekStrip } from './WeekStrip';

const DEFAULT_WEEKEND = [6, 7];

type Sheet =
  | { kind: 'quick' }
  | { kind: 'create'; date: string }
  | { kind: 'edit'; eventId: string }
  | null;

const VIEWS: { id: MobileView; label: string }[] = [
  { id: 'day', label: 'Day' },
  { id: 'month', label: 'Month' },
];

/** The calendar for phones (< 768 px): day view with a week strip, or a compact month. */
export function MobileCalendar() {
  const [today] = useState(todayIso);
  const [view, setView] = useState<MobileView>(loadView);
  const [selected, setSelected] = useState(today);
  const [sheet, setSheet] = useState<Sheet>(null);
  const queryClient = useQueryClient();

  const { data: auth } = useAuthState();
  const weekendDays = auth?.user?.weekend_days ?? DEFAULT_WEEKEND;
  const { data: categories } = useCategories();

  const rangeFor = view === 'day' ? dayRange : monthRange;
  const { from, to } = rangeFor(selected);
  const occurrences = useOccurrences(from, to, undefined, { keepPrevious: true });

  // Warm the neighbouring week / month so paging feels instant.
  useEffect(() => {
    const step = view === 'day' ? (d: string, n: number) => addDaysIso(d, 7 * n) : addMonthsIso;
    for (const n of [-1, 1]) {
      const range = rangeFor(step(selected, n));
      void queryClient.prefetchQuery(occurrencesQuery(range.from, range.to));
    }
  }, [view, selected, queryClient, rangeFor]);

  const visible = useMemo(
    () => filterVisible(occurrences.data, categories),
    [occurrences.data, categories],
  );
  const byDay = useMemo(() => groupByDay(visible, from, to), [visible, from, to]);

  const chooseView = (next: MobileView) => {
    setView(next);
    saveView(next);
  };
  const shiftWeek = (direction: -1 | 1) => setSelected((d) => addDaysIso(d, 7 * direction));
  const shiftMonth = (direction: -1 | 1) => setSelected((d) => addMonthsIso(d, direction));
  const swipeDay = useSwipe(shiftWeek);
  const swipeMonth = useSwipe(shiftMonth);
  const closeSheet = () => setSheet(null);
  const openEvent = (eventId: string) => setSheet({ kind: 'edit', eventId });

  return (
    <section aria-labelledby="calendar-heading" className="space-y-3 pb-20">
      <h1 id="calendar-heading" className="sr-only">
        Calendar
      </h1>
      <div className="flex items-center justify-between gap-2">
        <div role="group" aria-label="View" className="flex rounded-md border border-border">
          {VIEWS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              aria-pressed={view === id}
              onClick={() => chooseView(id)}
              className={`min-h-11 px-4 text-sm first:rounded-l-md last:rounded-r-md ${
                view === id ? 'bg-surface-muted font-medium' : 'text-text-muted'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button type="button" className={btnSecondary} onClick={() => setSelected(today)}>
          Today
        </button>
      </div>

      <CategoryChips scroll />

      {occurrences.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(occurrences.error)}
        </p>
      ) : null}

      {view === 'day' ? (
        <div className="space-y-3" {...swipeDay}>
          <WeekStrip
            selected={selected}
            today={today}
            weekendDays={weekendDays}
            byDay={byDay}
            onSelect={setSelected}
            onShiftWeek={shiftWeek}
          />
          <DayView
            date={selected}
            occurrences={byDay.get(selected) ?? []}
            loading={occurrences.isPending}
            onSelectEvent={openEvent}
          />
        </div>
      ) : (
        <div className="space-y-3" {...swipeMonth}>
          <div className="flex items-center justify-between gap-1">
            <button
              type="button"
              className={`${btnSecondary} w-11 px-0`}
              aria-label="Previous month"
              onClick={() => shiftMonth(-1)}
            >
              {'‹'}
            </button>
            <span className="text-base font-semibold">
              {format(parseIso(selected), 'MMMM yyyy')}
            </span>
            <button
              type="button"
              className={`${btnSecondary} w-11 px-0`}
              aria-label="Next month"
              onClick={() => shiftMonth(1)}
            >
              {'›'}
            </button>
          </div>
          <MonthView
            selected={selected}
            today={today}
            weekendDays={weekendDays}
            byDay={byDay}
            onSelect={setSelected}
            onSelectEvent={openEvent}
          />
        </div>
      )}

      <button
        type="button"
        aria-label="Add event"
        onClick={() => setSheet({ kind: 'quick' })}
        className="fixed bottom-[calc(4.5rem+env(safe-area-inset-bottom))] right-[calc(1rem+env(safe-area-inset-right))] z-20 flex size-14 items-center justify-center rounded-full bg-accent text-3xl leading-none text-accent-contrast shadow-lg"
      >
        <span aria-hidden="true">+</span>
      </button>

      {sheet?.kind === 'quick' ? (
        <QuickAddSheet
          date={selected}
          onClose={closeSheet}
          onMore={() => setSheet({ kind: 'create', date: selected })}
        />
      ) : null}
      {sheet?.kind === 'create' || sheet?.kind === 'edit' ? (
        <EventEditor
          variant="sheet"
          mode={sheet.kind}
          eventId={sheet.kind === 'edit' ? sheet.eventId : undefined}
          initialDate={sheet.kind === 'create' ? sheet.date : undefined}
          onClose={closeSheet}
        />
      ) : null}
    </section>
  );
}
