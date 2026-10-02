import { format } from 'date-fns';
import type { Occurrence } from '../../../api/types';
import { btnSecondary } from '../../../components/ui/classes';
import { isWeekend, parseIso } from '../../../lib/dates';
import { weekDays } from './mobileLib';

interface WeekStripProps {
  selected: string;
  today: string;
  weekendDays: readonly number[];
  /** Visible occurrences per ISO day. */
  byDay: ReadonlyMap<string, Occurrence[]>;
  onSelect(date: string): void;
  /** Moves the selection by whole weeks. */
  onShiftWeek(direction: -1 | 1): void;
}

const plural = (n: number) => `${n} ${n === 1 ? 'event' : 'events'}`;

/** Seven day buttons (Mon-Sun) with event dots; the host handles swipes. */
export function WeekStrip({
  selected,
  today,
  weekendDays,
  byDay,
  onSelect,
  onShiftWeek,
}: WeekStripProps) {
  const days = weekDays(selected);
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        className={`${btnSecondary} w-11 shrink-0 px-0`}
        aria-label="Previous week"
        onClick={() => onShiftWeek(-1)}
      >
        {'‹'}
      </button>
      <ul className="grid min-w-0 flex-1 grid-cols-7 gap-0.5" aria-label="Week">
        {days.map((day) => {
          const date = parseIso(day);
          const count = byDay.get(day)?.length ?? 0;
          const isSelected = day === selected;
          const isToday = day === today;
          return (
            <li key={day} className="min-w-0">
              <button
                type="button"
                aria-label={`${format(date, 'EEEE d MMMM')}, ${plural(count)}`}
                aria-current={isToday ? 'date' : undefined}
                aria-pressed={isSelected}
                data-date={day}
                onClick={() => onSelect(day)}
                className={`flex min-h-14 w-full flex-col items-center justify-center rounded-md border text-xs ${
                  isSelected
                    ? 'border-accent bg-accent text-accent-contrast'
                    : isToday
                      ? 'border-accent bg-today'
                      : isWeekend(date, weekendDays)
                        ? 'border-transparent bg-weekend'
                        : 'border-transparent bg-surface'
                }`}
              >
                <span aria-hidden="true">{format(date, 'EEEEE')}</span>
                <span aria-hidden="true" className="text-base font-semibold tabular-nums">
                  {format(date, 'd')}
                </span>
                <span aria-hidden="true" className="flex h-1.5 items-center">
                  {count > 0 ? (
                    <span
                      data-testid="week-dot"
                      className={`size-1.5 rounded-full ${
                        isSelected ? 'bg-accent-contrast' : 'bg-accent'
                      }`}
                    />
                  ) : null}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        className={`${btnSecondary} w-11 shrink-0 px-0`}
        aria-label="Next week"
        onClick={() => onShiftWeek(1)}
      >
        {'›'}
      </button>
    </div>
  );
}
