import { useState, type FormEvent } from 'react';
import type { Holiday, HolidayCalendar } from '../../api/types';
import { btnDanger, btnPrimary, btnSecondary, inputClass } from '../../components/ui/classes';
import { Dialog } from '../../components/ui/Dialog';
import { formatShortDate, todayIso } from '../../lib/dates';
import { describeError } from '../../lib/errors';
import { ColourPicker } from '../categories/ColourPicker';
import {
  calendarColour,
  useCalendarHolidays,
  useCreateHoliday,
  useDeleteHoliday,
  useHolidayCalendars,
  useResetCalendar,
  useUpdateCalendar,
  useUpdateHoliday,
} from '../holidays/api';
import { SettingsSection } from './SettingsSection';

/** Settings › Holidays: enable and colour each calendar, edit its holidays, reset to defaults. */
export function HolidaysSection() {
  const calendars = useHolidayCalendars();
  return (
    <SettingsSection id="holidays" title="Holidays">
      {calendars.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(calendars.error)}
        </p>
      ) : !calendars.data ? (
        <p className="text-sm text-text-muted">Loading...</p>
      ) : (
        <ul className="space-y-4">
          {calendars.data.map((calendar) => (
            <CalendarRow key={calendar.id} calendar={calendar} />
          ))}
        </ul>
      )}
    </SettingsSection>
  );
}

function CalendarRow({ calendar }: { calendar: HolidayCalendar }) {
  const update = useUpdateCalendar();
  const [editing, setEditing] = useState(false);
  return (
    <li className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex min-h-9 items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            checked={calendar.enabled}
            onChange={(e) =>
              update.mutate({ id: calendar.id, patch: { enabled: e.target.checked } })
            }
            className="size-4"
          />
          {calendar.name}
        </label>
        <ColourPicker
          label={`Colour for ${calendar.name} holidays`}
          value={calendarColour(calendar)}
          onChange={(colour) => update.mutate({ id: calendar.id, patch: { colour } })}
        />
        <button
          type="button"
          aria-expanded={editing}
          aria-label={`Edit holidays for ${calendar.name}`}
          onClick={() => setEditing((e) => !e)}
          className="ml-auto min-h-9 text-sm text-accent hover:underline"
        >
          Edit holidays
        </button>
      </div>
      {calendar.code === 'AE' ? (
        <p className="text-xs text-text-muted">
          Islamic holidays are estimates; check official announcements.
        </p>
      ) : null}
      {update.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(update.error)}
        </p>
      ) : null}
      {editing ? <CalendarEditor calendar={calendar} /> : null}
    </li>
  );
}

function CalendarEditor({ calendar }: { calendar: HolidayCalendar }) {
  const [year, setYear] = useState(() => Number(todayIso().slice(0, 4)));
  const list = useCalendarHolidays(calendar.id, year);
  const create = useCreateHoliday();
  const reset = useResetCalendar();
  const [date, setDate] = useState('');
  const [name, setName] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (!date || !name.trim()) return;
    setError(null);
    try {
      await create.mutateAsync({
        calendarId: calendar.id,
        body: { date, name: name.trim(), is_non_working: true },
      });
      setName('');
    } catch (e) {
      setError(describeError(e));
    }
  };

  return (
    <div className="space-y-3 rounded-md border border-border p-3">
      <div className="flex items-center gap-1">
        <button
          type="button"
          className={`${btnSecondary} px-2`}
          aria-label={`Previous year for ${calendar.name}`}
          onClick={() => setYear((y) => y - 1)}
        >
          {'‹'}
        </button>
        <span className="min-w-12 text-center text-sm font-semibold tabular-nums">{year}</span>
        <button
          type="button"
          className={`${btnSecondary} px-2`}
          aria-label={`Next year for ${calendar.name}`}
          onClick={() => setYear((y) => y + 1)}
        >
          {'›'}
        </button>
      </div>

      {list.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(list.error)}
        </p>
      ) : !list.data ? (
        <p className="text-sm text-text-muted">Loading...</p>
      ) : list.data.length === 0 ? (
        <p className="text-sm text-text-muted">No holidays in {year}</p>
      ) : (
        <ul aria-label={`${calendar.name} holidays ${year}`} className="space-y-2">
          {[...list.data]
            .sort((a, b) => a.date.localeCompare(b.date))
            .map((holiday) => (
              <HolidayRow key={`${holiday.id}:${holiday.name}`} holiday={holiday} />
            ))}
        </ul>
      )}

      <form onSubmit={(e) => void add(e)} className="flex flex-wrap items-end gap-2" noValidate>
        <div>
          <label htmlFor={`add-date-${calendar.id}`} className="block text-xs font-medium">
            Date
          </label>
          <input
            id={`add-date-${calendar.id}`}
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={inputClass}
          />
        </div>
        <div className="min-w-40 flex-1">
          <label htmlFor={`add-name-${calendar.id}`} className="block text-xs font-medium">
            Name
          </label>
          <input
            id={`add-name-${calendar.id}`}
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
          />
        </div>
        <button type="submit" className={btnSecondary} disabled={create.isPending}>
          Add holiday
        </button>
      </form>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      <button type="button" className={btnDanger} onClick={() => setConfirmReset(true)}>
        Reset to defaults
      </button>
      {confirmReset ? (
        <Dialog title={`Reset ${calendar.name} holidays`} onClose={() => setConfirmReset(false)}>
          <p className="text-sm">This removes your changes and added holidays for this calendar</p>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              className={btnPrimary}
              onClick={() => reset.mutate(calendar.id, { onSuccess: () => setConfirmReset(false) })}
            >
              Reset
            </button>
            <button type="button" className={btnSecondary} onClick={() => setConfirmReset(false)}>
              Cancel
            </button>
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}

function HolidayRow({ holiday }: { holiday: Holiday }) {
  const update = useUpdateHoliday();
  const remove = useDeleteHoliday();
  const [name, setName] = useState(holiday.name);
  const commitName = () => {
    const next = name.trim();
    if (!next) setName(holiday.name);
    else if (next !== holiday.name) update.mutate({ id: holiday.id, patch: { name: next } });
  };
  return (
    <li className="flex flex-wrap items-center gap-2 text-sm">
      <span className="w-24 shrink-0 tabular-nums text-text-muted">
        {formatShortDate(holiday.date)}
      </span>
      <input
        aria-label={`Name of holiday on ${holiday.date}`}
        value={name}
        maxLength={120}
        onChange={(e) => setName(e.target.value)}
        onBlur={commitName}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            commitName();
          }
        }}
        className={`${inputClass} min-w-40 flex-1`}
      />
      {holiday.estimated ? <span className="text-xs text-text-muted">(estimated)</span> : null}
      <label className="flex min-h-9 items-center gap-1.5">
        <input
          type="checkbox"
          aria-label={`Non-working ${holiday.date}`}
          checked={holiday.is_non_working}
          onChange={(e) =>
            update.mutate({ id: holiday.id, patch: { is_non_working: e.target.checked } })
          }
          className="size-4"
        />
        Non-working
      </label>
      <button
        type="button"
        className="min-h-9 px-2 text-danger hover:underline"
        aria-label={`Delete ${holiday.name}`}
        onClick={() => remove.mutate(holiday.id)}
      >
        Delete
      </button>
    </li>
  );
}
