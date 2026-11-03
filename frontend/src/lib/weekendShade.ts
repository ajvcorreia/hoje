import { useEffect } from 'react';
import { useAuthState } from '../app/useAuthState';
import { useMeSetting } from './meSetting';

/** How strongly weekends and days off are shaded (stored on the account; same list as the API). */
export const WEEKEND_SHADES = ['subtle', 'medium', 'strong', 'bold'] as const;
export type WeekendShade = (typeof WEEKEND_SHADES)[number];

/** Today's look: the theme's own weekend colour. */
export const DEFAULT_WEEKEND_SHADE: WeekendShade = 'subtle';

export const isWeekendShade = (value: unknown): value is WeekendShade =>
  typeof value === 'string' && (WEEKEND_SHADES as readonly string[]).includes(value);

/** The weekend shading, saved on the account. */
export function useWeekendShade(): [WeekendShade, (value: WeekendShade) => void] {
  const [value, setValue] = useMeSetting('weekend_shade', DEFAULT_WEEKEND_SHADE);
  return [isWeekendShade(value) ? value : DEFAULT_WEEKEND_SHADE, setValue];
}

/** Applies the account's shading to this page: `data-weekend-shade` on <html> (see tokens.css). */
export function useWeekendShadeSync(): void {
  const { data } = useAuthState();
  const shade = data?.user?.weekend_shade;
  useEffect(() => {
    const root = document.documentElement;
    if (isWeekendShade(shade) && shade !== DEFAULT_WEEKEND_SHADE) {
      root.setAttribute('data-weekend-shade', shade);
    } else {
      root.removeAttribute('data-weekend-shade');
    }
  }, [shade]);
}
