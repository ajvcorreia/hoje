import { useIsDesktop } from '../../lib/useIsDesktop';
import { DesktopCalendar } from './DesktopCalendar';
import { MobileCalendar } from './mobile/MobileCalendar';

/** Calendar route: the desktop calendar at >= 768 px, the mobile day/month views on phones. */
export function CalendarPage() {
  const desktop = useIsDesktop();
  return desktop ? <DesktopCalendar /> : <MobileCalendar />;
}
