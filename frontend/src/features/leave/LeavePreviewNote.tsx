import type { LeaveImpact } from '../../api/types';
import { daysLabel, formatDays } from './api';

/**
 * What a vacation booking does to the balance: "Uses 5 working days · 12 left in 2026", plus
 * a non-blocking warning for every year it overdraws.
 */
export function LeavePreviewNote({ impacts }: { impacts: readonly LeaveImpact[] | undefined }) {
  if (!impacts || impacts.length === 0) return null;
  const over = impacts.filter((i) => i.exceeds);
  const shown = impacts.filter((i, index) => index === 0 || i.exceeds);
  const multiYear = impacts.length > 1;
  return (
    <div className="space-y-1 text-sm">
      {shown.map((i) => (
        <p key={i.year} className="text-text-muted">
          Uses {daysLabel(i.days, 'working day')} · {formatDays(Math.max(0, i.remaining_after))}{' '}
          left in {i.year}
        </p>
      ))}
      {over.map((i) => (
        <p key={i.year} role="alert" className="font-medium text-danger">
          This is {daysLabel(-i.remaining_after)} over your remaining balance
          {multiYear ? ` in ${i.year}` : ''}
        </p>
      ))}
    </div>
  );
}

/** Toast text when a saved booking overdraws, or null. */
export function overdrawMessage(impacts: readonly LeaveImpact[] | undefined): string | null {
  const over = impacts?.find((i) => i.exceeds);
  return over
    ? `Vacation balance exceeded: ${daysLabel(-over.remaining_after)} over in ${over.year}`
    : null;
}
