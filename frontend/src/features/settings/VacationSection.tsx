import { useState, type FormEvent } from 'react';
import { btnSecondary } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { todayIso } from '../../lib/dates';
import { describeError } from '../../lib/errors';
import { formatDays, useLeaveBalance, useSavePolicy } from '../leave/api';
import { SettingsSection } from './SettingsSection';

/** Settings › Vacation: per-year allowance and carry-over; saved on blur or Enter. */
export function VacationSection() {
  const [year, setYear] = useState(() => Number(todayIso().slice(0, 4)));
  const balance = useLeaveBalance(year);
  return (
    <SettingsSection id="vacation" title="Vacation">
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
      </div>
      {balance.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(balance.error)}
        </p>
      ) : balance.data ? (
        <PolicyForm
          key={year}
          year={year}
          allowance={balance.data.allowance_days}
          carriedOver={balance.data.carried_over_days}
        />
      ) : (
        <p className="text-sm text-text-muted">Loading...</p>
      )}
      <p className="text-sm text-text-muted">
        Events in categories marked &lsquo;Counts as vacation&rsquo; use working days, excluding
        weekends and enabled holidays.
      </p>
    </SettingsSection>
  );
}

function PolicyForm({
  year,
  allowance,
  carriedOver,
}: {
  year: number;
  allowance: number;
  carriedOver: number;
}) {
  const save = useSavePolicy();
  const [allowanceText, setAllowanceText] = useState(formatDays(allowance));
  const [carriedText, setCarriedText] = useState(formatDays(carriedOver));
  const [saved, setSaved] = useState({ allowance, carriedOver });
  const [state, setState] = useState<'idle' | 'saved' | 'invalid'>('idle');
  const [error, setError] = useState<string | null>(null);

  const commit = async () => {
    const a = Number(allowanceText);
    const c = Number(carriedText);
    if (allowanceText.trim() === '' || carriedText.trim() === '' || !(a >= 0) || !(c >= 0)) {
      setState('invalid');
      return;
    }
    if (a === Number(saved.allowance) && c === Number(saved.carriedOver)) return;
    setError(null);
    try {
      await save.mutateAsync({ year, values: { allowance_days: a, carried_over_days: c } });
      setSaved({ allowance: a, carriedOver: c });
      setState('saved');
    } catch (e) {
      setError(describeError(e));
      setState('idle');
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void commit();
  };
  const onEdit = (set: (v: string) => void) => (value: string) => {
    set(value);
    setState('idle');
  };

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Field
          label="Allowance (days)"
          type="number"
          step={0.5}
          min={0}
          inputMode="decimal"
          value={allowanceText}
          onChange={(e) => onEdit(setAllowanceText)(e.target.value)}
          onBlur={() => void commit()}
        />
        <Field
          label="Carried over (days)"
          type="number"
          step={0.5}
          min={0}
          inputMode="decimal"
          value={carriedText}
          onChange={(e) => onEdit(setCarriedText)(e.target.value)}
          onBlur={() => void commit()}
        />
      </div>
      <button type="submit" hidden>
        Save
      </button>
      {state === 'saved' ? (
        <p role="status" className="text-sm text-text-muted">
          Saved
        </p>
      ) : null}
      {state === 'invalid' ? (
        <p role="alert" className="text-sm text-danger">
          Enter zero or a positive number of days.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </form>
  );
}
