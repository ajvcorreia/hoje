import { useState } from 'react';
import { Link } from 'react-router';
import { Dialog } from '../../components/ui/Dialog';
import { Popover } from '../../components/ui/Popover';
import { formatShortDate, todayIso } from '../../lib/dates';
import { describeError } from '../../lib/errors';
import { useIsDesktop } from '../../lib/useIsDesktop';
import { EventEditor } from '../events/EventEditor';
import { daysLabel, formatDays, pillText, useHasVacationCategory, useLeaveBalance } from './api';

const currentYear = () => Number(todayIso().slice(0, 4));

/** Header pill "Vacation: N left" (hidden without a vacation category) and its balance panel. */
export function VacationPill() {
  const hasVacation = useHasVacationCategory();
  const isDesktop = useIsDesktop();
  const [year] = useState(currentYear);
  const balance = useLeaveBalance(year, hasVacation);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  if (!hasVacation) return null;

  const remaining = balance.data ? Number(balance.data.remaining) : null;
  const over = remaining !== null && remaining < 0;
  const close = () => setOpen(false);
  const panel = (
    <VacationPanel
      onClose={close}
      onSelectBooking={(eventId) => {
        setOpen(false);
        setEditing(eventId);
      }}
    />
  );

  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={(event) => {
          setAnchor(event.currentTarget);
          setOpen((o) => !o);
        }}
        className={`inline-flex min-h-9 items-center whitespace-nowrap rounded-full border border-border px-3 text-xs font-medium hover:bg-surface-muted md:min-h-8 ${
          over ? 'text-danger' : 'text-text'
        }`}
      >
        {remaining === null ? 'Vacation' : pillText(remaining)}
      </button>
      {open && isDesktop && anchor ? (
        <Popover anchor={anchor} label="Vacation balance" placement="below" onClose={close}>
          {panel}
        </Popover>
      ) : null}
      {open && !isDesktop ? (
        <Dialog title="Vacation balance" onClose={close}>
          {panel}
        </Dialog>
      ) : null}
      {editing ? (
        <EventEditor
          mode="edit"
          eventId={editing}
          variant={isDesktop ? 'dialog' : 'sheet'}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </>
  );
}

function VacationPanel({
  onClose,
  onSelectBooking,
}: {
  onClose(): void;
  onSelectBooking(eventId: string): void;
}) {
  const [year, setYear] = useState(currentYear);
  const balance = useLeaveBalance(year);
  const data = balance.data;
  const rows: [string, number | undefined][] = [
    ['Allowance', data?.allowance_days],
    ['Carried over', data?.carried_over_days],
    ['Used', data?.used],
    ['Planned', data?.planned],
    ['Remaining', data?.remaining],
  ];
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center justify-between">
        <button
          type="button"
          aria-label="Previous year"
          onClick={() => setYear((y) => y - 1)}
          className="min-h-9 min-w-9 rounded-md hover:bg-surface-muted"
        >
          {'‹'}
        </button>
        <span className="font-semibold tabular-nums">{year}</span>
        <button
          type="button"
          aria-label="Next year"
          onClick={() => setYear((y) => y + 1)}
          className="min-h-9 min-w-9 rounded-md hover:bg-surface-muted"
        >
          {'›'}
        </button>
      </div>

      {balance.isError ? (
        <p role="alert" className="text-danger">
          {describeError(balance.error)}
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
            {rows.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className={label === 'Remaining' ? 'font-semibold' : 'text-text-muted'}>
                  {label}
                </dt>
                <dd
                  className={`text-right tabular-nums ${
                    label === 'Remaining'
                      ? `font-semibold ${Number(value) < 0 ? 'text-danger' : ''}`
                      : ''
                  }`}
                >
                  {value === undefined ? '…' : formatDays(value)}
                </dd>
              </div>
            ))}
          </dl>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Bookings
            </h3>
            {data && data.bookings.length === 0 ? (
              <p className="mt-1 text-text-muted">No vacation booked</p>
            ) : (
              <ul aria-label="Bookings" className="mt-1 max-h-48 space-y-0.5 overflow-y-auto">
                {data?.bookings.map((b) => (
                  <li key={`${b.event_id}:${b.start_date}`}>
                    <button
                      type="button"
                      onClick={() => onSelectBooking(b.event_id)}
                      className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left hover:bg-surface-muted md:min-h-9"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block break-words font-medium">{b.title}</span>
                        <span className="block break-words text-xs text-text-muted">
                          {b.start_date === b.end_date
                            ? formatShortDate(b.start_date)
                            : `${formatShortDate(b.start_date)} – ${formatShortDate(b.end_date)}`}
                        </span>
                      </span>
                      <span className="shrink-0 tabular-nums text-text-muted">
                        {daysLabel(b.days)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      <Link
        to="/settings#vacation"
        onClick={onClose}
        className="inline-flex min-h-9 items-center text-accent hover:underline"
      >
        Edit allowance
      </Link>
    </div>
  );
}
