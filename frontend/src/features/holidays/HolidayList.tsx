import { CategorySwatch } from '../categories/CategorySwatch';
import { holidayLabel, type HolidayDay } from './api';

/** The holidays of one day, non-interactive: swatch + "Portugal · Freedom Day (estimated)". */
export function HolidayList({ holidays }: { holidays: readonly HolidayDay[] | undefined }) {
  if (!holidays || holidays.length === 0) return null;
  return (
    <ul aria-label="Holidays" className="space-y-0.5">
      {holidays.map((h) => (
        <li key={h.id} className="flex items-center gap-2 px-2 py-1 text-sm italic">
          <CategorySwatch colour={h.colour} />
          <span className="min-w-0 flex-1">{holidayLabel(h)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Mobile day view: one card per holiday, same look as event cards but not tappable. */
export function HolidayCards({ holidays }: { holidays: readonly HolidayDay[] | undefined }) {
  if (!holidays || holidays.length === 0) return null;
  return (
    <ul aria-label="Holidays" className="space-y-2">
      {holidays.map((h) => (
        <li
          key={h.id}
          data-cat={h.colour}
          className="m-card flex min-h-14 flex-col justify-center rounded-md px-3 py-2"
        >
          <span className="break-words text-sm font-medium italic">{h.name}</span>
          <span className="break-words text-xs text-text-muted">
            {[h.calendarName, h.estimated ? 'estimated' : '']
              .filter(Boolean)
              .join(' · ')}
          </span>
        </li>
      ))}
    </ul>
  );
}
