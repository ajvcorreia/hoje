import { useEffect } from 'react';
import { useAuthState } from '../app/useAuthState';
import { isHex } from '../styles/customColour';
import { useMeSetting } from './meSetting';

/** Outline each event in its category's own (text) colour. */
export const CATEGORY_OUTLINE = 'category';

/** Shown in the colour picker while the outline follows the categories. */
export const DEFAULT_OUTLINE_HEX = '#1f2937';

/** A thin outline around events in the calendar (saved on the account). */
export function useEventOutline(): [boolean, (value: boolean) => void] {
  return useMeSetting('event_outline', false);
}

/** Its colour: 'category' or a `#rrggbb` the user picked. */
export function useEventOutlineColour(): [string, (value: string) => void] {
  return useMeSetting('event_outline_colour', CATEGORY_OUTLINE);
}

/**
 * Applies the account's outline to this page: `data-event-outline` on <html> switches it on
 * (see calendar.css) and `--ev-outline` holds a picked colour (unset: each category's own).
 */
export function useEventOutlineSync(): void {
  const { data } = useAuthState();
  const on = Boolean(data?.user?.event_outline);
  const colour = data?.user?.event_outline_colour;
  useEffect(() => {
    const root = document.documentElement;
    if (on) root.setAttribute('data-event-outline', '');
    else root.removeAttribute('data-event-outline');
    if (on && colour && isHex(colour)) root.style.setProperty('--ev-outline', colour);
    else root.style.removeProperty('--ev-outline');
  }, [on, colour]);
}
