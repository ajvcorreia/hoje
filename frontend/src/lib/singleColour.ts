import { useMeSetting } from './meSetting';

/** The colour offered until the user picks one (same default as the API). */
export const DEFAULT_SINGLE_COLOUR = 'blue';

/** Draw every event in one colour instead of its category's (saved on the account). */
export function useSingleColour(): [boolean, (value: boolean) => void] {
  return useMeSetting('single_colour', false);
}

/** That one colour: a palette name or a `#rrggbb`. Kept while the switch is off. */
export function useSingleColourValue(): [string, (value: string) => void] {
  return useMeSetting('single_colour_value', DEFAULT_SINGLE_COLOUR);
}
