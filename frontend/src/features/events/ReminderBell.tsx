import { BellIcon } from '../../app/icons';
import type { Event } from '../../api/types';

/** A small bell for events with reminders; the accessible label is "Has reminder". */
export function ReminderBell({ event }: { event: Pick<Event, 'reminders'> }) {
  if (event.reminders.length === 0) return null;
  return (
    <span role="img" aria-label="Has reminder" title="Has reminder" className="shrink-0">
      <BellIcon width={14} height={14} className="text-text-muted" />
    </span>
  );
}
