import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../api/client';
import type { components } from '../api/schema';
import { AUTH_STATE_KEY, useAuthState } from '../app/useAuthState';
import { ME_KEY } from '../features/settings/api';

type Me = components['schemas']['Me'];
type MeUpdate = components['schemas']['MeUpdate'];
type AuthData = { user?: Me | null } | undefined;

/**
 * One per-user setting stored on the account: read from the signed-in user (`fallback` while
 * loading), written with an optimistic PATCH /api/v1/me that is rolled back when it fails.
 */
export function useMeSetting<K extends keyof Me & keyof MeUpdate>(
  field: K,
  fallback: Me[K],
): [Me[K], (value: Me[K]) => void] {
  const qc = useQueryClient();
  const { data } = useAuthState();
  const value = (data?.user?.[field] ?? fallback) as Me[K];

  const mutation = useMutation({
    meta: { protected: true },
    mutationFn: async (next: Me[K]) =>
      unwrap(await api.PATCH('/api/v1/me', { body: { [field]: next } as MeUpdate })),
    onMutate: (next) => {
      const prev = {
        auth: qc.getQueryData<AuthData>(AUTH_STATE_KEY),
        me: qc.getQueryData<Me>(ME_KEY),
      };
      qc.setQueryData(AUTH_STATE_KEY, (s: AuthData) =>
        s?.user ? { ...s, user: { ...s.user, [field]: next } } : s,
      );
      qc.setQueryData(ME_KEY, (me: Me | undefined) => (me ? { ...me, [field]: next } : me));
      return prev;
    },
    onError: (_error, _next, prev) => {
      if (!prev) return;
      qc.setQueryData(AUTH_STATE_KEY, prev.auth);
      qc.setQueryData(ME_KEY, prev.me);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: AUTH_STATE_KEY }),
  });
  return [value, (next) => mutation.mutate(next)];
}
