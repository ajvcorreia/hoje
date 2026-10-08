import { CategorySwatch } from '../categories/CategorySwatch';
import { CAKE, birthdayName, holidayLabel, isBirthday, type HolidayDay } from './api';

/**
 * The holidays and birthdays of one day, non-interactive: swatch + "Portugal · Freedom Day
 * (estimated)", then "🎂 Ana (34)" for synced birthdays.
 */
export function HolidayList({ holidays }: { holidays: readonly HolidayDay[] | undefined }) {
  const plain = holidays?.filter((h) => !isBirthday(h)) ?? [];
  const birthdays = holidays?.filter(isBirthday) ?? [];
  return (
    <>
      {plain.length > 0 ? (
        <ul aria-label="Holidays" className="space-y-0.5">
          {plain.map((h) => (
            <li key={h.id} className="flex items-center gap-2 px-2 py-1 text-sm italic">
              <CategorySwatch colour={h.colour} />
              <span className="min-w-0 flex-1 break-words">{holidayLabel(h)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {birthdays.length > 0 ? (
        <ul aria-label="Birthdays" className="space-y-0.5">
          {birthdays.map((h) => (
            <li key={h.id} className="flex items-center gap-2 px-2 py-1 text-sm">
              <span aria-hidden="true">{CAKE}</span>
              <span className="min-w-0 flex-1 break-words">{birthdayName(h)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

/** Mobile day view: one card per holiday or birthday, same look as event cards, not tappable. */
export function HolidayCards({ holidays }: { holidays: readonly HolidayDay[] | undefined }) {
  const plain = holidays?.filter((h) => !isBirthday(h)) ?? [];
  const birthdays = holidays?.filter(isBirthday) ?? [];
  return (
    <>
      {plain.length > 0 ? (
        <ul aria-label="Holidays" className="space-y-2">
          {plain.map((h) => (
            <li
              key={h.id}
              data-cat={h.colour}
              className="m-card flex min-h-14 flex-col justify-center rounded-md px-3 py-2"
            >
              <span className="break-words text-sm font-medium italic">{h.name}</span>
              <span className="break-words text-xs text-text-muted">
                {[h.calendarName, h.estimated ? 'estimated' : ''].filter(Boolean).join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {birthdays.length > 0 ? (
        <ul aria-label="Birthdays" className="space-y-2">
          {birthdays.map((h) => (
            <li
              key={h.id}
              data-cat={h.colour}
              className="m-card flex min-h-14 flex-col justify-center rounded-md px-3 py-2"
            >
              <span className="break-words text-sm font-medium">
                <span aria-hidden="true">{CAKE} </span>
                {h.name}
              </span>
              <span className="break-words text-xs text-text-muted">
                {h.age ? `Birthday · turns ${h.age}` : 'Birthday'}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
