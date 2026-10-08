import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../api/client';
import type { components } from '../api/schema';
import { AUTH_STATE_KEY, useAuthState } from '../app/useAuthState';
import { ME_KEY } from '../features/settings/api';

export const DEFAULT_DAILY_SUMMARY_TIME = '07:00';

type Me = components['schemas']['Me'];
type Change = { daily_summary_enabled?: boolean; daily_summary_time?: string };

/** Whether `value` is a complete 24 hour `HH:MM` time, as the API requires. */
export function isSummaryTime(value: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
}

/**
 * The daily summary email preference of the signed-in user. Stored on the user like
 * {@link useMaxEvents}: read from the auth state, written with an optimistic PATCH /api/v1/me
 * that is rolled back when the request fails. The time is the wall-clock time in the user's
 * time zone.
 */
export function useDailySummary() {
  const qc = useQueryClient();
  const { data } = useAuthState();
  const user = data?.user;
  const enabled = user?.daily_summary_enabled ?? false;
  const time = user?.daily_summary_time ?? DEFAULT_DAILY_SUMMARY_TIME;
  const timezone = user?.timezone ?? 'UTC';

  type AuthData = { user?: Me | null } | undefined;
  const mutation = useMutation({
    meta: { protected: true },
    mutationFn: async (change: Change) => unwrap(await api.PATCH('/api/v1/me', { body: change })),
    onMutate: (change) => {
      const prev = {
        auth: qc.getQueryData<AuthData>(AUTH_STATE_KEY),
        me: qc.getQueryData<Me>(ME_KEY),
      };
      qc.setQueryData(AUTH_STATE_KEY, (s: AuthData) =>
        s?.user ? { ...s, user: { ...s.user, ...change } } : s,
      );
      qc.setQueryData(ME_KEY, (me: Me | undefined) => (me ? { ...me, ...change } : me));
      return prev;
    },
    onError: (_error, _change, prev) => {
      if (!prev) return;
      qc.setQueryData(AUTH_STATE_KEY, prev.auth);
      qc.setQueryData(ME_KEY, prev.me);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: AUTH_STATE_KEY }),
  });
  return {
    enabled,
    time,
    timezone,
    setEnabled: (value: boolean) => mutation.mutate({ daily_summary_enabled: value }),
    setTime: (value: string) => {
      if (isSummaryTime(value)) mutation.mutate({ daily_summary_time: value });
    },
    error: mutation.isError ? mutation.error : null,
  };
}
