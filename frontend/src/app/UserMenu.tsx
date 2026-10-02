import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { useLogout } from '../features/auth/api';
import { useAuthState } from './useAuthState';

/** Desktop-only account menu: on mobile, "Log out" lives in Settings. */
export function UserMenu() {
  const { data } = useAuthState();
  const logout = useLogout();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const email = data?.user?.email;

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!email) return null;

  return (
    <div ref={rootRef} className="relative hidden md:block">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${email}`}
        onClick={() => setOpen((o) => !o)}
        className="flex size-8 items-center justify-center rounded-full border border-border bg-surface-muted text-sm font-medium uppercase"
      >
        {email.charAt(0)}
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="Account"
          className="absolute right-0 top-10 z-20 w-56 rounded-md border border-border bg-surface py-1 text-sm"
        >
          <p className="truncate px-3 py-2 text-xs text-text-muted">{email}</p>
          <Link
            role="menuitem"
            to="/settings"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 hover:bg-surface-muted"
          >
            Settings
          </Link>
          <button
            type="button"
            role="menuitem"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
            className="block w-full px-3 py-2 text-left hover:bg-surface-muted"
          >
            Log out
          </button>
        </div>
      ) : null}
    </div>
  );
}
