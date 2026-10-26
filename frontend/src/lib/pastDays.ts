import type { CSSProperties } from 'react';
import { useMeSetting } from './meSetting';
import { usePastStripeColour } from './pastStripeColour';
import { useStrikePast } from './strikePast';

/** How past days are marked (stored on the user; same lists as the API). */
export const PAST_STYLES = ['stripes', 'crosshatch', 'line', 'cross', 'fade'] as const;
export type PastStyle = (typeof PAST_STYLES)[number];
export const PAST_STRENGTHS = ['light', 'medium', 'strong'] as const;
export type PastStrength = (typeof PAST_STRENGTHS)[number];

export const DEFAULT_PAST_STYLE: PastStyle = 'stripes';
export const DEFAULT_PAST_STRENGTH: PastStrength = 'medium';

export const isPastStyle = (value: unknown): value is PastStyle =>
  typeof value === 'string' && (PAST_STYLES as readonly string[]).includes(value);
export const isPastStrength = (value: unknown): value is PastStrength =>
  typeof value === 'string' && (PAST_STRENGTHS as readonly string[]).includes(value);

/**
 * "Strike through past days": the account's choice once saved; until then this device's own
 * switch (it used to be per device). Switching saves both.
 */
export function useStrikePastSetting(): [boolean, (value: boolean) => void] {
  const [account, setAccount] = useMeSetting('strike_past', null);
  const [device, setDevice] = useStrikePast();
  return [
    account ?? device,
    (value) => {
      setDevice(value);
      setAccount(value);
    },
  ];
}

export function usePastStyle(): [PastStyle, (value: PastStyle) => void] {
  const [value, setValue] = useMeSetting('past_style', DEFAULT_PAST_STYLE);
  return [isPastStyle(value) ? value : DEFAULT_PAST_STYLE, setValue];
}

export function usePastStrength(): [PastStrength, (value: PastStrength) => void] {
  const [value, setValue] = useMeSetting('past_strength', DEFAULT_PAST_STRENGTH);
  return [isPastStrength(value) ? value : DEFAULT_PAST_STRENGTH, setValue];
}

/**
 * Whether past days are marked, plus what a view's root carries for calendar.css: the style and
 * strength attributes and the colour variable. Cells before today get `data-past`.
 */
export function usePastDays(): {
  strike: boolean;
  attrs: { 'data-past-style': PastStyle; 'data-past-strength': PastStrength };
  vars: CSSProperties;
} {
  const [strike] = useStrikePastSetting();
  const [style] = usePastStyle();
  const [strength] = usePastStrength();
  const [colour] = usePastStripeColour();
  return {
    strike,
    attrs: { 'data-past-style': style, 'data-past-strength': strength },
    vars: { '--past-stripe': colour } as CSSProperties,
  };
}
