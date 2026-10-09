import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../api/client';
import type { components } from '../api/schema';
import { AUTH_STATE_KEY, useAuthState } from '../app/useAuthState';
import { ME_KEY } from '../features/settings/api';

/** Grey, the colour the stripes over past days always had unless the user picks another. */
export const DEFAULT_PAST_STRIPE_COLOUR = '#9ca3af';

type Me = components['schemas']['Me'];

/**
 * The colour of the diagonal stripes over past days in the month grid. Stored on the user like
 * {@link useVerticalTextSize}: read from the signed-in user (default grey while loading), written
 * with an optimistic PATCH /api/v1/me that is rolled back when the request fails.
 */
export function usePastStripeColour(): [string, (value: string) => void] {
  const qc = useQueryClient();
  const { data } = useAuthState();
  const value = data?.user?.past_stripe_colour ?? DEFAULT_PAST_STRIPE_COLOUR;

  type AuthData = { user?: Me | null } | undefined;
  const mutation = useMutation({
    meta: { protected: true },
    mutationFn: async (colour: string) =>
      unwrap(await api.PATCH('/api/v1/me', { body: { past_stripe_colour: colour } })),
    onMutate: (colour) => {
      const prev = {
        auth: qc.getQueryData<AuthData>(AUTH_STATE_KEY),
        me: qc.getQueryData<Me>(ME_KEY),
      };
      qc.setQueryData(AUTH_STATE_KEY, (s: AuthData) =>
        s?.user ? { ...s, user: { ...s.user, past_stripe_colour: colour } } : s,
      );
      qc.setQueryData(ME_KEY, (me: Me | undefined) =>
        me ? { ...me, past_stripe_colour: colour } : me,
      );
      return prev;
    },
    onError: (_error, _colour, prev) => {
      if (!prev) return;
      qc.setQueryData(AUTH_STATE_KEY, prev.auth);
      qc.setQueryData(ME_KEY, prev.me);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: AUTH_STATE_KEY }),
  });
  return [value, (next) => mutation.mutate(next)];
}
