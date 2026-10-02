import { useCallback, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import type { Category, Occurrence } from '../../api/types';
import {
  WEEKDAY_LETTERS,
  addDaysIso,
  formatDayHeading,
  monthMatrix,
  monthName,
} from '../../lib/dates';
import { groupByDay } from '../events/occurrences';

interface YearViewProps {
  year: number;
  /** Occurrences of the year, already filtered for hidden categories. */
  occurrences: Occurrence[];
  categories: Category[];
  today: string;
  onOpenDay(date: string, anchor: HTMLElement): void;
}

const MAX_DOTS = 3;

function dayLabel(iso: string, year: number, count: number): string {
  const base = `${formatDayHeading(iso)} ${year}`;
  return count > 0 ? `${base}, ${count} ${count === 1 ? 'event' : 'events'}` : base;
}

/**
 * Year overview: twelve classic mini months. A day is shaded with its first event's
 * category colour and carries up to three dots for further events. Opens the same day
 * popover as the month grid.
 */
export function YearView({ year, occurrences, categories, today, onOpenDay }: YearViewProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const colourOf = useMemo(() => new Map(categories.map((c) => [c.id, c.colour])), [categories]);
  const byDay = useMemo(
    () => groupByDay(occurrences, `${year}-01-01`, `${year}-12-31`),
    [occurrences, year],
  );
  const defaultFocus = today.startsWith(`${year}-`) ? today : `${year}-01-01`;
  const [focusDate, setFocusDate] = useState(defaultFocus);
  const activeFocus = focusDate.startsWith(`${year}-`) ? focusDate : defaultFocus;

  const onClick = useCallback(
    (event: MouseEvent) => {
      const cell = (event.target as HTMLElement).closest<HTMLElement>('[data-date]');
      if (cell?.dataset.date) onOpenDay(cell.dataset.date, cell);
    },
    [onOpenDay],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      const step =
        event.key === 'ArrowLeft'
          ? -1
          : event.key === 'ArrowRight'
            ? 1
            : event.key === 'ArrowUp'
              ? -7
              : event.key === 'ArrowDown'
                ? 7
                : 0;
      const cell = (event.target as HTMLElement).closest<HTMLElement>('[data-date]');
      if (!step || !cell?.dataset.date) return;
      event.preventDefault();
      const next = addDaysIso(cell.dataset.date, step);
      if (!next.startsWith(`${year}-`)) return;
      setFocusDate(next);
      rootRef.current?.querySelector<HTMLElement>(`[data-date="${next}"]`)?.focus();
    },
    [year],
  );

  return (
    // The wrapper only delegates pointer/keyboard events from the day buttons inside it.
    <div
      ref={rootRef}
      role="presentation"
      className="min-h-0 flex-1 overflow-y-auto"
      onClick={onClick}
      onKeyDown={onKeyDown}
    >
      <div className="grid grid-cols-[repeat(auto-fill,minmax(14rem,1fr))] gap-4 pb-2">
        {Array.from({ length: 12 }, (_, month) => (
          <section
            key={month}
            aria-label={`${monthName(month)} ${year}`}
            className="rounded-lg border border-border-strong bg-surface p-2"
          >
            <h3 className="mb-1 px-1 text-sm font-semibold">{monthName(month)}</h3>
            <div
              className="grid grid-cols-7 text-center text-[10px] text-text-muted"
              aria-hidden="true"
            >
              {WEEKDAY_LETTERS.map((letter, i) => (
                <span key={i}>{letter}</span>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-px">
              {monthMatrix(year, month)
                .flat()
                .map((iso, i) => {
                  if (!iso) return <span key={i} />;
                  const events = byDay.get(iso) ?? [];
                  const first = events[0];
                  const dots = Math.min(MAX_DOTS, Math.max(0, events.length - 1));
                  return (
                    <button
                      key={iso}
                      type="button"
                      className="yr-day"
                      data-date={iso}
                      data-today={iso === today || undefined}
                      data-cat={first ? colourOf.get(first.event.category_id) : undefined}
                      tabIndex={iso === activeFocus ? 0 : -1}
                      aria-label={dayLabel(iso, year, events.length)}
                      onFocus={() => setFocusDate(iso)}
                    >
                      <span aria-hidden="true">{Number(iso.slice(8))}</span>
                      {dots > 0 ? (
                        <span className="yr-dots" aria-hidden="true">
                          {events.slice(1, 1 + dots).map((o) => (
                            <i
                              key={o.event_id + o.occurrence_start}
                              className="yr-dot"
                              data-cat={colourOf.get(o.event.category_id)}
                            />
                          ))}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
