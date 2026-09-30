import { useQuery } from '@tanstack/react-query';
import { api, unwrap } from '../api/client';
import { csrfStore } from '../api/csrf';

export const AUTH_STATE_KEY = ['auth', 'state'] as const;

/** Session/auth state. Also keeps the CSRF token store in sync with the server. */
export function useAuthState() {
  return useQuery({
    queryKey: AUTH_STATE_KEY,
    queryFn: async () => {
      const state = unwrap(await api.GET('/api/v1/auth/state'));
      csrfStore.set(state.csrf_token);
      return state;
    },
  });
}
