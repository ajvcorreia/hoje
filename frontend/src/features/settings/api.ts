import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../../api/client';
import { AUTH_STATE_KEY } from '../../app/useAuthState';

export const ME_KEY = ['me'] as const;
export const EMAIL_SETTINGS_KEY = ['settings', 'email'] as const;

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/me')),
  });
}

export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: { timezone?: string; weekend_days?: number[] }) =>
      unwrap(await api.PATCH('/api/v1/me', { body })),
    onSuccess: (me) => {
      qc.setQueryData(ME_KEY, me);
      return qc.invalidateQueries({ queryKey: AUTH_STATE_KEY });
    },
  });
}

export function useEmailSettings() {
  return useQuery({
    queryKey: EMAIL_SETTINGS_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/settings/email')),
  });
}

export const EMAIL_LOG_KEY = ['settings', 'email', 'log'] as const;

export function useEmailLog() {
  return useQuery({
    queryKey: EMAIL_LOG_KEY,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/settings/email/log', { params: { query: { limit: 20 } } })),
  });
}

export function useSendTestEmail() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async () => {
      unwrap(await api.POST('/api/v1/settings/email/test'));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: EMAIL_LOG_KEY }),
  });
}

export function useChangePassword() {
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: { current_password: string; new_password: string }) => {
      unwrap(await api.POST('/api/v1/auth/password/change', { body }));
    },
  });
}

function useRefreshMe() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ME_KEY }),
      qc.invalidateQueries({ queryKey: AUTH_STATE_KEY }),
    ]);
}

export function useTwoFactorSetup() {
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: { password: string }) =>
      unwrap(await api.POST('/api/v1/auth/2fa/setup', { body })),
  });
}

export function useTwoFactorEnable() {
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: { code: string }) =>
      unwrap(await api.POST('/api/v1/auth/2fa/enable', { body })),
  });
}

export function useTwoFactorDisable() {
  const refresh = useRefreshMe();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: { password: string; code: string }) => {
      unwrap(await api.POST('/api/v1/auth/2fa/disable', { body }));
    },
    onSuccess: refresh,
  });
}

export function useRegenerateRecoveryCodes() {
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: { password: string; code: string }) =>
      unwrap(await api.POST('/api/v1/auth/2fa/recovery-codes', { body })),
  });
}

/** Refresh `me` + auth state after the 2FA enable flow is finished. */
export { useRefreshMe };
