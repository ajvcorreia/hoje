import { useMeSetting } from './meSetting';

/** Grey, the colour the stripes over past days have unless the user picks another. */
export const DEFAULT_PAST_STRIPE_COLOUR = '#9ca3af';

/** The colour of the diagonal stripes over past days in the month grid (stored on the user). */
export function usePastStripeColour(): [string, (value: string) => void] {
  return useMeSetting('past_stripe_colour', DEFAULT_PAST_STRIPE_COLOUR);
}
