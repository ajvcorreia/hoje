import type { Occurrence } from '../../api/types';
import { Popover } from '../../components/ui/Popover';
import { formatDayHeading } from '../../lib/dates';
import { DayEventList } from '../events/DayEventList';
import { QuickAdd } from '../events/QuickAdd';
import type { HolidayDay } from '../holidays/api';
import { HolidayList } from '../holidays/HolidayList';

interface DayPopoverProps {
  date: string;
  anchor: HTMLElement;
  /** That day's visible occurrences. */
  occurrences: Occurrence[];
  /** That day's holidays, listed before the events. */
  holidays?: HolidayDay[];
  onClose(): void;
  /** Open the editor for an existing event. */
  onSelectEvent(eventId: string): void;
  /** Open the full editor for a new event on this date. */
  onAddWithDetails(date: string): void;
}

/**
 * Popover opened by clicking a day: the date, that day's holidays and events and the
 * type-to-add field (focused immediately; Enter creates an all-day event and closes the popover).
 */
export function DayPopover({
  date,
  anchor,
  occurrences,
  holidays,
  onClose,
  onSelectEvent,
  onAddWithDetails,
}: DayPopoverProps) {
  const heading = formatDayHeading(date);
  return (
    <Popover anchor={anchor} label={`Events on ${heading}`} onClose={onClose}>
      <h2 className="text-sm font-semibold">{heading}</h2>
      <div className="my-2 max-h-64 overflow-y-auto">
        <HolidayList holidays={holidays} />
        <DayEventList date={date} occurrences={occurrences} onSelect={onSelectEvent} />
      </div>
      <QuickAdd date={date} onCreated={onClose} />
      <button
        type="button"
        onClick={() => onAddWithDetails(date)}
        className="mt-2 min-h-8 text-xs text-accent hover:underline"
      >
        Add with details
      </button>
    </Popover>
  );
}
