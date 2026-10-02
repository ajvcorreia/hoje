import { btnSecondary } from '../../../components/ui/classes';
import { Dialog } from '../../../components/ui/Dialog';
import { formatDayHeading } from '../../../lib/dates';
import { QuickAdd } from '../../events/QuickAdd';

interface QuickAddSheetProps {
  date: string;
  onClose(): void;
  /** Open the full editor for the same date. */
  onMore(): void;
}

/** Compact bottom sheet: title field (Enter saves with the default category) and "More". */
export function QuickAddSheet({ date, onClose, onMore }: QuickAddSheetProps) {
  return (
    <Dialog title={`Add event · ${formatDayHeading(date)}`} onClose={onClose}>
      <div className="space-y-3 pb-[env(safe-area-inset-bottom)]">
        <QuickAdd date={date} inputId="m-sheet-quick-add" onCreated={onClose} />
        <button type="button" className={btnSecondary} onClick={onMore}>
          More
        </button>
      </div>
    </Dialog>
  );
}
