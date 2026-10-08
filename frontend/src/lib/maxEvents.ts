import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../api/client';
import type { components } from '../api/schema';
import { AUTH_STATE_KEY, useAuthState } from '../app/useAuthState';
import { ME_KEY } from '../features/settings/api';

export const MIN_MAX_EVENTS = 1;
export const MAX_MAX_EVENTS = 6;
/** Two side-by-side halves, as the month grid always drew them. */
export const DEFAULT_MAX_EVENTS = 2;

type Me = components['schemas']['Me'];

/** Clamps to the allowed range; anything that is not a number gives the default. */
export function clampMaxEvents(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return DEFAULT_MAX_EVENTS;
  return Math.min(MAX_MAX_EVENTS, Math.max(MIN_MAX_EVENTS, Math.round(n)));
}

/**
 * How many events one day of the month grid shows before "+N". Stored on the user, so it follows
 * them across devices: read from the signed-in user (default 2 while loading), written with an
 * optimistic PATCH /api/v1/me that is rolled back when the request fails.
 */
export function useMaxEvents(): [number, (value: number) => void] {
  const qc = useQueryClient();
  const { data } = useAuthState();
  const value = clampMaxEvents(data?.user?.max_events_per_day ?? DEFAULT_MAX_EVENTS);

  type AuthData = { user?: Me | null } | undefined;
  const mutation = useMutation({
    meta: { protected: true },
    mutationFn: async (n: number) =>
      unwrap(await api.PATCH('/api/v1/me', { body: { max_events_per_day: n } })),
    onMutate: (n) => {
      const prev = {
        auth: qc.getQueryData<AuthData>(AUTH_STATE_KEY),
        me: qc.getQueryData<Me>(ME_KEY),
      };
      qc.setQueryData(AUTH_STATE_KEY, (s: AuthData) =>
        s?.user ? { ...s, user: { ...s.user, max_events_per_day: n } } : s,
      );
      qc.setQueryData(ME_KEY, (me: Me | undefined) => (me ? { ...me, max_events_per_day: n } : me));
      return prev;
    },
    onError: (_error, _n, prev) => {
      if (!prev) return;
      qc.setQueryData(AUTH_STATE_KEY, prev.auth);
      qc.setQueryData(ME_KEY, prev.me);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: AUTH_STATE_KEY }),
  });
  return [value, (next) => mutation.mutate(clampMaxEvents(next))];
}
