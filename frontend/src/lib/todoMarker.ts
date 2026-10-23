import type { CSSProperties } from 'react';
import { ink, isHex } from '../styles/customColour';
import { useMeSetting } from './meSetting';

/** How calendar days with open to-dos are marked (stored on the user; same list as the API). */
export const TODO_MARKERS = ['ring', 'bar', 'badge', 'triangle'] as const;
export type TodoMarker = (typeof TODO_MARKERS)[number];

export const DEFAULT_TODO_MARKER: TodoMarker = 'ring';

export const isTodoMarker = (value: unknown): value is TodoMarker =>
  typeof value === 'string' && (TODO_MARKERS as readonly string[]).includes(value);

/** The to-do marker of the Months and Year views, saved on the account so it follows the user. */
export function useTodoMarker(): [TodoMarker, (value: TodoMarker) => void] {
  const [value, setValue] = useMeSetting('todo_marker', DEFAULT_TODO_MARKER);
  return [isTodoMarker(value) ? value : DEFAULT_TODO_MARKER, setValue];
}

/** 'auto': the theme's amber (see calendar.css); otherwise a `#rrggbb` the user picked. */
export const AUTO_TODO_MARKER_COLOUR = 'auto';

/** Shown in the colour picker while the colour is 'auto' (the light theme's amber). */
export const DEFAULT_TODO_MARKER_HEX = '#d97706';

/** The to-do marker colour, saved on the account like the style. */
export function useTodoMarkerColour(): [string, (value: string) => void] {
  return useMeSetting('todo_marker_colour', AUTO_TODO_MARKER_COLOUR);
}

/** CSS variables for a picked colour (with white or black badge text); none for 'auto'. */
export function todoMarkerStyle(colour: string): CSSProperties {
  if (!isHex(colour)) return {};
  return { '--todo': colour, '--todo-text': ink(colour) } as CSSProperties;
}
