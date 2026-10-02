import { Navigate, Outlet, useLocation } from 'react-router';
import { Spinner } from '../components/ui/Spinner';
import { useAuthState } from './useAuthState';

/** Route guard for everything behind a login. */
export function RequireAuth() {
  const state = useAuthState();
  const location = useLocation();

  if (state.isPending) return <Spinner />;
  // Network/5xx failure: keep the shell up; it shows the "API not ready" notice.
  if (state.isError) return <Outlet />;

  const auth = state.data;
  const loggedIn = auth.authenticated && auth.stage !== 'mfa_pending';
  if (loggedIn) return <Outlet />;

  if (auth.registration_open && auth.stage !== 'mfa_pending') {
    return <Navigate to="/setup" replace />;
  }
  const path = location.pathname + location.search;
  const target = path === '/' ? '/login' : `/login?next=${encodeURIComponent(path)}`;
  return <Navigate to={target} replace />;
}
