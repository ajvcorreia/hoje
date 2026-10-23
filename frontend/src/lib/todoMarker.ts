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
