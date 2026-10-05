import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../../api/client';
import { fetchAuthState, AUTH_STATE_KEY } from '../../app/useAuthState';

/** Mutation helper: after an auth change, refresh the auth state (and with it the CSRF token). */
function useRefreshAuth() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: AUTH_STATE_KEY });
}

export function useLogin() {
  const refresh = useRefreshAuth();
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) =>
      unwrap(await api.POST('/api/v1/auth/login', { body })),
    onSuccess: refresh,
  });
}

export function useLoginMfa() {
  const refresh = useRefreshAuth();
  return useMutation({
    mutationFn: async (body: { code: string }) => {
      unwrap(await api.POST('/api/v1/auth/login/mfa', { body }));
    },
    onSuccess: refresh,
  });
}

export function useRegister() {
  const refresh = useRefreshAuth();
  return useMutation({
    mutationFn: async (body: { email: string; password: string; setup_token?: string }) => {
      unwrap(await api.POST('/api/v1/auth/register', { body }));
      // The new session has a new CSRF token: pick it up before the next unsafe request.
      await fetchAuthState();
      try {
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (timezone) await api.PATCH('/api/v1/me', { body: { timezone } });
      } catch {
        // The account exists; the timezone can be set later in Settings.
      }
    },
    onSuccess: refresh,
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      unwrap(await api.POST('/api/v1/auth/logout'));
    },
    onSuccess: async () => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'auth' });
      await qc.invalidateQueries({ queryKey: AUTH_STATE_KEY });
    },
  });
}

export function useForgotPassword() {
  return useMutation({
    mutationFn: async (body: { email: string }) => {
      unwrap(await api.POST('/api/v1/auth/password/forgot', { body }));
    },
  });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: async (body: { token: string; new_password: string }) => {
      unwrap(await api.POST('/api/v1/auth/password/reset', { body }));
    },
  });
}
