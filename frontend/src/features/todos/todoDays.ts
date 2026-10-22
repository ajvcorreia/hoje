import type { Todo } from '../../api/types';

/** A count of open to-dos per day, for the calendar's to-do marker. */
export type TodoDays = ReadonlyMap<string, number>;

export const NO_TODO_DAYS: TodoDays = new Map();

/**
 * The days to mark: each open to-do counts on its due date, or, without one, on the day it is
 * listed (today, unless it was added for a later day). Done to-dos are not counted.
 */
export function todoDays(todos: readonly Pick<Todo, 'done' | 'due_date' | 'shown_on'>[]): TodoDays {
  const days = new Map<string, number>();
  for (const todo of todos) {
    if (todo.done) continue;
    const day = todo.due_date ?? todo.shown_on;
    days.set(day, (days.get(day) ?? 0) + 1);
  }
  return days;
}

/** ", 2 to-dos" for a day's accessible name, or nothing. */
export const todoAria = (count: number | undefined): string =>
  count ? `, ${count} ${count === 1 ? 'to-do' : 'to-dos'}` : '';
