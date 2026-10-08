import { useCallback, useMemo, useState } from 'react';
import type { Event as HojeEvent } from '../../api/types';
import { useAuthState } from '../../app/useAuthState';
import { btnSecondary } from '../../components/ui/classes';
import { describeError } from '../../lib/errors';
import { useToday } from '../../lib/useToday';
import { useCategories } from '../categories/api';
import { CategoryChips } from '../categories/CategoryChips';
import { useOccurrences } from '../events/api';
import { EventEditor } from '../events/EventEditor';
import { filterVisible, groupByDay } from '../events/occurrences';
import { useCalendarOverlay } from '../birthdays/api';
import { AgendaView } from './AgendaView';
import { DayPopover } from './DayPopover';
import { MonthGrid, type ScrollRequest } from './MonthGrid';
import { SearchBox } from './SearchBox';
import { YearView } from './YearView';

type View = 'months' | 'year' | 'agenda';

const VIEWS: { id: View; label: string }[] = [
  { id: 'months', label: 'Months' },
  { id: 'year', label: 'Year' },
  { id: 'agenda', label: 'Agenda' },
];

const DEFAULT_WEEKEND = [6, 7];

type EditorState = { mode: 'create'; date: string } | { mode: 'edit'; eventId: string };

/** The calendar for screens >= 768 px: toolbar, the three views, day popover and editor. */
export function DesktopCalendar() {
  const today = useToday();
  const [view, setView] = useState<View>('months');
  const [year, setYear] = useState(() => Number(today.slice(0, 4)));
  const [popover, setPopover] = useState<{ date: string; anchor: HTMLElement } | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [scrollRequest, setScrollRequest] = useState<ScrollRequest | null>(() => ({
    month: Number(today.slice(5, 7)) - 1,
    nonce: 0,
  }));

  const { data: auth } = useAuthState();
  const weekendDays = auth?.user?.weekend_days ?? DEFAULT_WEEKEND;
  const { data: categories } = useCategories();
  const from = `${year}-01-01`;
  const to = `${year}-12-31`;
  const occurrences = useOccurrences(from, to);

  const visible = useMemo(
    () => filterVisible(occurrences.data, categories),
    [occurrences.data, categories],
  );
  const byDay = useMemo(() => groupByDay(visible, from, to), [visible, from, to]);
  const categoryList = categories ?? [];
  const holidays = useCalendarOverlay(year); // holidays and birthdays

  const openDay = useCallback((date: string, anchor: HTMLElement) => {
    setPopover({ date, anchor });
  }, []);
  const closePopover = useCallback(() => setPopover(null), []);

  const goToday = () => {
    setYear(Number(today.slice(0, 4)));
    setScrollRequest((r) => ({ month: Number(today.slice(5, 7)) - 1, nonce: (r?.nonce ?? 0) + 1 }));
    if (view !== 'months') setView('months');
  };

  const pickSearchResult = (event: HojeEvent) => {
    setYear(Number(event.start_date.slice(0, 4)));
    setView('months');
    setScrollRequest((r) => ({
      month: Number(event.start_date.slice(5, 7)) - 1,
      nonce: (r?.nonce ?? 0) + 1,
    }));
    setEditor({ mode: 'edit', eventId: event.id });
  };

  return (
    <section aria-labelledby="calendar-heading" className="flex min-h-0 flex-1 flex-col gap-2">
      <h1 id="calendar-heading" className="sr-only">
        Calendar
      </h1>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div role="group" aria-label="View" className="flex rounded-md border border-border">
          {VIEWS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              aria-pressed={view === id}
              onClick={() => setView(id)}
              className={`min-h-9 px-3 text-sm first:rounded-l-md last:rounded-r-md ${
                view === id ? 'bg-surface-muted font-medium' : 'text-text-muted hover:text-text'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            className={`${btnSecondary} px-2`}
            aria-label="Previous year"
            onClick={() => setYear((y) => y - 1)}
          >
            {'‹'}
          </button>
          <span className="min-w-12 text-center text-sm font-semibold tabular-nums">{year}</span>
          <button
            type="button"
            className={`${btnSecondary} px-2`}
            aria-label="Next year"
            onClick={() => setYear((y) => y + 1)}
          >
            {'›'}
          </button>
          <button type="button" className={btnSecondary} onClick={goToday}>
            Today
          </button>
        </div>

        <CategoryChips className="min-w-0 flex-1" />
        <SearchBox onPick={pickSearchResult} />
      </div>

      {occurrences.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(occurrences.error)}
        </p>
      ) : null}

      {view === 'months' ? (
        <MonthGrid
          year={year}
          occurrences={visible}
          categories={categoryList}
          weekendDays={weekendDays}
          today={today}
          onOpenDay={openDay}
          scrollRequest={scrollRequest}
          holidays={holidays}
        />
      ) : view === 'year' ? (
        <YearView
          year={year}
          occurrences={visible}
          categories={categoryList}
          today={today}
          onOpenDay={openDay}
          holidays={holidays}
        />
      ) : (
        <AgendaView
          today={today}
          onSelectEvent={(eventId) => setEditor({ mode: 'edit', eventId })}
        />
      )}

      {popover ? (
        <DayPopover
          key={popover.date}
          date={popover.date}
          anchor={popover.anchor}
          occurrences={byDay.get(popover.date) ?? []}
          holidays={holidays.get(popover.date)}
          onClose={closePopover}
          onSelectEvent={(eventId) => {
            setPopover(null);
            setEditor({ mode: 'edit', eventId });
          }}
          onAddWithDetails={(date) => {
            setPopover(null);
            setEditor({ mode: 'create', date });
          }}
        />
      ) : null}

      {editor ? (
        <EventEditor
          mode={editor.mode}
          eventId={editor.mode === 'edit' ? editor.eventId : undefined}
          initialDate={editor.mode === 'create' ? editor.date : undefined}
          onClose={() => setEditor(null)}
        />
      ) : null}
    </section>
  );
}
