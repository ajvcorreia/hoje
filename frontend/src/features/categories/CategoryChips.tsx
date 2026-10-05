import { useShowBirthdays } from '../../lib/showBirthdays';
import { useShowHolidays } from '../../lib/showHolidays';
import { useFelizAnnivStatus } from '../birthdays/api';
import { CAKE, calendarColour, useHolidayCalendars } from '../holidays/api';
import { useCategories, useUpdateCategory } from './api';
import { CategorySwatch } from './CategorySwatch';

/**
 * Category filter chips: one toggle per category; pressed = shown. Toggling persists the
 * category's `hidden` flag (`PATCH /categories/{id}`), so the choice follows the user
 * across devices. A final "Holidays" chip (per device) shows or hides the holiday overlays;
 * it only appears while a holiday calendar is enabled. A "Birthdays" chip (per device) does the
 * same for synced FelizAnniv birthdays once there are any. Shared by the desktop header and
 * the mobile calendar.
 */
export function CategoryChips({
  className = '',
  scroll = false,
}: {
  className?: string;
  /** One horizontally scrollable row with 44 px targets (mobile) instead of wrapping. */
  scroll?: boolean;
}) {
  const { data: categories } = useCategories();
  const { data: calendars } = useHolidayCalendars();
  const update = useUpdateCategory();
  const [showHolidays, setShowHolidays] = useShowHolidays();
  const [showBirthdays, setShowBirthdays] = useShowBirthdays();
  const { data: felizanniv } = useFelizAnnivStatus();
  const enabledCalendar = calendars?.find((c) => c.enabled);
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
        return (
          <button
            key={category.id}
            type="button"
            aria-pressed={shown}
            onClick={() => update.mutate({ category, patch: { hidden: shown } })}
            className={`${chip} ${
              shown ? 'bg-surface text-text' : 'bg-transparent text-text-muted line-through'
            }`}
          >
            <CategorySwatch colour={category.colour} className={shown ? '' : 'opacity-40'} />
            {category.name}
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
