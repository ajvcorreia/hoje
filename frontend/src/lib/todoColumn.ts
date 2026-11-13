import { useMeSetting } from './meSetting';

/** Where the to-do column sits beside the calendar (stored on the account; same list as the API). */
export const TODO_COLUMNS = ['off', 'left', 'right'] as const;
export type TodoColumnPlace = (typeof TODO_COLUMNS)[number];

export const isTodoColumnPlace = (value: unknown): value is TodoColumnPlace =>
  typeof value === 'string' && (TODO_COLUMNS as readonly string[]).includes(value);

/** The to-do column's place, saved on the account ('off' hides it). */
export function useTodoColumn(): [TodoColumnPlace, (value: TodoColumnPlace) => void] {
  const [value, setValue] = useMeSetting('todo_column', 'off');
  return [isTodoColumnPlace(value) ? value : 'off', setValue];
}
