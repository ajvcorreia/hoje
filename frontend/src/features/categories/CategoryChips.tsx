import { useMemo } from 'react';
import type { Occurrence } from '../../api/types';
import { useShowBirthdays } from '../../lib/showBirthdays';
import { useShowHolidays } from '../../lib/showHolidays';
import { useFelizAnnivStatus } from '../birthdays/api';
import { CAKE, calendarColour, useHolidayCalendars } from '../holidays/api';
import { useCategories, useUpdateCategory } from './api';
import { CategorySwatch } from './CategorySwatch';
import { useCategoryIcon } from './icons';
import { countByCategory, formatCount, fullFormat } from './counts';

/**
 * Category filter chips: one toggle per category; pressed = shown. Toggling persists the
 * category's `hidden` flag (`PATCH /categories/{id}`), so the choice follows the user
 * across devices. A final "Holidays" chip (per device) shows or hides the holiday overlays;
 * it only appears while a holiday calendar is enabled. A "Birthdays" chip (per device) does the
 * same for synced FelizAnniv birthdays once there are any. Shared by the desktop header and
 * the mobile calendar.
 *
 * Each category chip carries a count: the number of event occurrences of that category in the
 * range the calendar shows (`occurrences`: desktop = the viewed year, mobile = the visible
 * week / month), regardless of the chip being toggled off. Holidays / Birthdays chips have no
 * count: their data is not fetched while their chip is off.
 */
export function CategoryChips({
  className = '',
  scroll = false,
  occurrences,
}: {
  className?: string;
  /** One horizontally scrollable row with 44 px targets (mobile) instead of wrapping. */
  scroll?: boolean;
  /** All occurrences loaded for the shown range, NOT filtered by hidden categories. */
  occurrences?: readonly Occurrence[];
}) {
  const { data: categories } = useCategories();
  const { data: calendars } = useHolidayCalendars();
  const update = useUpdateCategory();
  const [showHolidays, setShowHolidays] = useShowHolidays();
  const [showBirthdays, setShowBirthdays] = useShowBirthdays();
  const { data: felizanniv } = useFelizAnnivStatus();
  const iconOf = useCategoryIcon('pills');
  const enabledCalendar = calendars?.find((c) => c.enabled);
  const counts = useMemo(() => countByCategory(occurrences), [occurrences]);
  const hasBirthdays = !!felizanniv?.configured && felizanniv.count > 0;
  if ((!categories || categories.length === 0) && !enabledCalendar && !hasBirthdays) return null;
  const chip = `inline-flex items-center gap-1.5 rounded-full border border-border text-xs ${
    scroll ? 'min-h-11 shrink-0 whitespace-nowrap px-3' : 'min-h-8 px-2.5 md:min-h-7'
  }`;
  return (
    <div
      role="group"
      aria-label="Show categories"
      className={`flex gap-1 ${scroll ? 'flex-nowrap overflow-x-auto' : 'flex-wrap'} ${className}`}
    >
      {(categories ?? []).map((category) => {
        const shown = !category.hidden;
        const count = counts.get(category.id) ?? 0;
        return (
          <button
            key={category.id}
            type="button"
            aria-pressed={shown}
            aria-label={`${category.name}, ${fullFormat.format(count)} ${count === 1 ? 'event' : 'events'}`}
            onClick={() => update.mutate({ category, patch: { hidden: shown } })}
            className={`${chip} ${
              shown ? 'bg-surface text-text' : 'bg-transparent text-text-muted'
            }`}
          >
            <CategorySwatch
              colour={category.colour}
              icon={iconOf(category.id)}
              className={shown ? '' : 'opacity-40'}
            />
            <span className={shown ? '' : 'line-through'}>{category.name}</span>
            <span
              aria-hidden="true"
              data-testid="category-count"
              className="text-[0.6875rem] tabular-nums text-text-muted"
            >
              {formatCount(count)}
            </span>
          </button>
        );
      })}
      {enabledCalendar ? (
        <button
          type="button"
          aria-pressed={showHolidays}
          onClick={() => setShowHolidays(!showHolidays)}
          className={`${chip} italic ${
            showHolidays ? 'bg-surface text-text' : 'bg-transparent text-text-muted line-through'
          }`}
        >
          <CategorySwatch
            colour={calendarColour(enabledCalendar)}
            className={showHolidays ? '' : 'opacity-40'}
          />
          Holidays
        </button>
      ) : null}
      {hasBirthdays ? (
        <button
          type="button"
          aria-pressed={showBirthdays}
          onClick={() => setShowBirthdays(!showBirthdays)}
          className={`${chip} ${
            showBirthdays ? 'bg-surface text-text' : 'bg-transparent text-text-muted line-through'
          }`}
        >
          <span aria-hidden="true" className={showBirthdays ? '' : 'opacity-40'}>
            {CAKE}
          </span>
          Birthdays
        </button>
      ) : null}
    </div>
  );
}
