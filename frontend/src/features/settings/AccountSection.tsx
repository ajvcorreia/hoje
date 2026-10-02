import { useMemo, useState } from 'react';
import { inputClass } from '../../components/ui/classes';
import { describeError } from '../../lib/errors';
import { useMe, useUpdateMe } from './api';
import { SettingsSection } from './SettingsSection';

const WEEKDAYS = [
  { iso: 1, label: 'Mon' },
  { iso: 2, label: 'Tue' },
  { iso: 3, label: 'Wed' },
  { iso: 4, label: 'Thu' },
  { iso: 5, label: 'Fri' },
  { iso: 6, label: 'Sat' },
  { iso: 7, label: 'Sun' },
] as const;

function allTimeZones(current: string): string[] {
  let zones: string[] = [];
  try {
    zones = Intl.supportedValuesOf('timeZone');
  } catch {
    zones = [];
  }
  if (!zones.includes('UTC')) zones = ['UTC', ...zones];
  if (current && !zones.includes(current)) zones = [current, ...zones];
  return zones;
}

export function AccountSection() {
  const me = useMe();
  const update = useUpdateMe();
  const [filter, setFilter] = useState('');
  const current = me.data?.timezone ?? '';
  const zones = useMemo(() => allTimeZones(current), [current]);

  const needle = filter.trim().toLowerCase().replace(/ /g, '_');
  const visible = zones.filter((z) => z === current || z.toLowerCase().includes(needle));

  if (me.isPending) {
    return (
      <SettingsSection title="Account">
        <p className="text-sm text-text-muted">Loading...</p>
      </SettingsSection>
    );
  }
  if (me.isError) {
    return (
      <SettingsSection title="Account">
        <p role="alert" className="text-sm text-danger">
          {describeError(me.error)}
        </p>
      </SettingsSection>
    );
  }

  const weekend = me.data.weekend_days;
  const toggleDay = (iso: number) => {
    const next = weekend.includes(iso) ? weekend.filter((d) => d !== iso) : [...weekend, iso];
    update.mutate({ weekend_days: next.sort((a, b) => a - b) });
  };

  return (
    <SettingsSection title="Account">
      <div>
        <p className="text-sm font-medium">Email</p>
        <p className="mt-1 text-sm text-text-muted">{me.data.email}</p>
      </div>

      <div>
        <label htmlFor="tz" className="block text-sm font-medium">
          Time zone
        </label>
        <input
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter time zones"
          aria-label="Filter time zones"
          className={`${inputClass} mt-2`}
        />
        <select
          id="tz"
          value={current}
          onChange={(e) => update.mutate({ timezone: e.target.value })}
          className={`${inputClass} mt-2`}
        >
          {visible.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
      </div>

      <div>
        <p id="weekend-label" className="text-sm font-medium">
          Weekend days
        </p>
        <div role="group" aria-labelledby="weekend-label" className="mt-2 flex flex-wrap gap-2">
          {WEEKDAYS.map(({ iso, label }) => {
            const on = weekend.includes(iso);
            return (
              <button
                key={iso}
                type="button"
                aria-pressed={on}
                onClick={() => toggleDay(iso)}
                className={`min-h-11 min-w-11 rounded-md border px-3 text-sm md:min-h-9 ${
                  on
                    ? 'border-accent bg-accent text-accent-contrast'
                    : 'border-border bg-surface text-text hover:bg-surface-muted'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div role="status" className="min-h-5 text-sm text-text-muted">
        {update.isSuccess ? 'Saved' : null}
      </div>
      {update.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(update.error)}
        </p>
      ) : null}
    </SettingsSection>
  );
}
