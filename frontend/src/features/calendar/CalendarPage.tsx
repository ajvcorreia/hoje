import { useIsDesktop } from '../../lib/useIsDesktop';
import { DesktopCalendar } from './DesktopCalendar';

/** Calendar route: the desktop calendar at >= 768 px, a placeholder on phones for now. */
export function CalendarPage() {
  const desktop = useIsDesktop();
  if (desktop) return <DesktopCalendar />;
  return (
    <section aria-labelledby="calendar-heading">
      <h1 id="calendar-heading" className="text-lg font-semibold">
        Calendar
      </h1>
      <p className="mt-2 text-sm text-text-muted">Mobile view coming soon</p>
    </section>
  );
}
