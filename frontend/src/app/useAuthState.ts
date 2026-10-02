import { useQuery } from '@tanstack/react-query';
import { api, unwrap } from '../api/client';
import { csrfStore } from '../api/csrf';

export const AUTH_STATE_KEY = ['auth', 'state'] as const;

/** Fetches the auth state and keeps the CSRF token store in sync with the server. */
export async function fetchAuthState() {
  const state = unwrap(await api.GET('/api/v1/auth/state'));
  csrfStore.set(state.csrf_token);
  return state;
}

/** Session/auth state. Also keeps the CSRF token store in sync with the server. */
export function useAuthState() {
  return useQuery({
    queryKey: AUTH_STATE_KEY,
    queryFn: fetchAuthState,
    // An errored state must not flip back to pending when another component mounts.
    retryOnMount: false,
  });
}
