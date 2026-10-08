import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../api/client';
import type { components } from '../api/schema';
import { AUTH_STATE_KEY, useAuthState } from '../app/useAuthState';
import { ME_KEY } from '../features/settings/api';

export const MIN_VERTICAL_TEXT_SIZE = 8;
export const MAX_VERTICAL_TEXT_SIZE = 32;
/** The size rotated labels always had at the default text size. */
export const DEFAULT_VERTICAL_TEXT_SIZE = 12;

type Me = components['schemas']['Me'];

/** Clamps to the allowed range; anything that is not a number gives the default. */
export function clampVerticalTextSize(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return DEFAULT_VERTICAL_TEXT_SIZE;
  return Math.min(MAX_VERTICAL_TEXT_SIZE, Math.max(MIN_VERTICAL_TEXT_SIZE, Math.round(n)));
}

/**
 * The preferred font size (px) of the rotated multi-day labels in the month grid; a label only
 * shrinks below it when its name does not fit the block height. Stored on the user like
 * {@link useMaxEvents}: read from the signed-in user (default 12 while loading), written with an
 * optimistic PATCH /api/v1/me that is rolled back when the request fails.
 */
export function useVerticalTextSize(): [number, (value: number) => void] {
  const qc = useQueryClient();
  const { data } = useAuthState();
  const value = clampVerticalTextSize(data?.user?.vertical_text_size ?? DEFAULT_VERTICAL_TEXT_SIZE);

  type AuthData = { user?: Me | null } | undefined;
  const mutation = useMutation({
    meta: { protected: true },
    mutationFn: async (n: number) =>
      unwrap(await api.PATCH('/api/v1/me', { body: { vertical_text_size: n } })),
    onMutate: (n) => {
      const prev = {
        auth: qc.getQueryData<AuthData>(AUTH_STATE_KEY),
        me: qc.getQueryData<Me>(ME_KEY),
      };
      qc.setQueryData(AUTH_STATE_KEY, (s: AuthData) =>
        s?.user ? { ...s, user: { ...s.user, vertical_text_size: n } } : s,
      );
      qc.setQueryData(ME_KEY, (me: Me | undefined) => (me ? { ...me, vertical_text_size: n } : me));
      return prev;
    },
    onError: (_error, _n, prev) => {
      if (!prev) return;
      qc.setQueryData(AUTH_STATE_KEY, prev.auth);
      qc.setQueryData(ME_KEY, prev.me);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: AUTH_STATE_KEY }),
  });
  return [value, (next) => mutation.mutate(clampVerticalTextSize(next))];
}
