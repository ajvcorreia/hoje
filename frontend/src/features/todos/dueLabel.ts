import type { Todo } from '../../api/types';
import { formatShortDate, todayIso } from '../../lib/dates';

/** "Due today", "Overdue · 5 Oct 2026" or "Due 12 Oct 2026"; null without a due date. */
export function dueLabel(todo: Pick<Todo, 'due_date'>): { text: string; overdue: boolean } | null {
  if (!todo.due_date) return null;
  const today = todayIso();
  if (todo.due_date === today) return { text: 'Due today', overdue: false };
  const date = formatShortDate(todo.due_date);
  return todo.due_date < today
    ? { text: `Overdue · ${date}`, overdue: true }
    : { text: `Due ${date}`, overdue: false };
}
