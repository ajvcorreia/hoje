import { NavLink, Outlet } from 'react-router';
import { CalendarIcon, SettingsIcon } from './icons';
import { useAuthState } from './useAuthState';

const NAV_ITEMS = [
  { to: '/', label: 'Calendar', Icon: CalendarIcon, end: true },
  { to: '/settings', label: 'Settings', Icon: SettingsIcon, end: false },
] as const;

function ApiNotice() {
  const { isError } = useAuthState();
  if (!isError) return null;
  return (
    <div
      role="status"
      className="border-b border-border bg-surface-muted px-4 py-1 text-center text-xs text-text-muted"
    >
      API not ready
    </div>
  );
}

function HeaderNav() {
  return (
    <nav aria-label="Main" className="hidden gap-1 md:flex">
      {NAV_ITEMS.map(({ to, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `rounded-md px-3 py-1.5 text-sm ${
              isActive ? 'bg-surface-muted font-medium' : 'text-text-muted hover:text-text'
            }`
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function BottomNav() {
  return (
    <nav
      aria-label="Main (mobile)"
      className="fixed inset-x-0 bottom-0 z-10 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] md:hidden"
    >
      <ul className="flex">
        {NAV_ITEMS.map(({ to, label, Icon, end }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex min-h-14 min-w-11 flex-col items-center justify-center gap-0.5 text-xs ${
                  isActive ? 'font-medium text-accent' : 'text-text-muted'
                }`
              }
            >
              <Icon />
              <span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function AppShell() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-2 focus:text-accent-contrast"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-10 border-b border-border bg-surface pt-[env(safe-area-inset-top)]">
        <div className="mx-auto flex h-12 max-w-6xl items-center gap-4 px-4">
          <span className="text-base font-semibold tracking-tight">Hoje</span>
          <HeaderNav />
          {/* Slot for the future "Vacation: N left" pill and filter/search. */}
          <div data-slot="header-actions" className="ml-auto flex items-center gap-2" />
        </div>
      </header>
      <ApiNotice />
      <main
        id="main"
        tabIndex={-1}
        className="mx-auto w-full max-w-6xl flex-1 px-4 py-4 pb-[calc(4.5rem+env(safe-area-inset-bottom))] outline-none md:pb-4"
      >
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
