import type { ReactNode } from 'react';
import type { Todo } from '../../api/types';
import { formatShortDate } from '../../lib/dates';
import { useUpdateTodo } from './api';
import { dueLabel } from './dueLabel';

interface TodoCheckProps {
  todo: Todo;
  /** Also say where a carried-over to-do started ("from 3 Oct 2026"). */
  showOrigin?: boolean;
  /** Extra controls at the end of the row (for example Delete). */
  children?: ReactNode;
}

/** One to-do: a checkbox with its title, due date and, when carried over, its first day. */
export function TodoCheck({ todo, showOrigin, children }: TodoCheckProps) {
  const update = useUpdateTodo();
  const due = todo.done ? null : dueLabel(todo);
  const origin = showOrigin && !todo.done && todo.day < todo.shown_on;
  return (
    <li className="flex items-center gap-0.5">
      <label className="flex min-h-11 min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-surface-muted md:min-h-9">
        <input
          type="checkbox"
          checked={todo.done}
          onChange={(e) => update.mutate({ id: todo.id, patch: { done: e.target.checked } })}
          className="size-4 shrink-0 accent-[var(--color-accent)]"
        />
        <span className="min-w-0 flex-1">
          <span className={`block break-words ${todo.done ? 'text-text-muted line-through' : ''}`}>
            {todo.title}
          </span>
          {(due || origin) && (
            <span className="block break-words text-xs text-text-muted">
              {due && (
                <span className={due.overdue ? 'font-medium text-danger' : undefined}>
                  {due.text}
                </span>
              )}
              {due && origin && ' · '}
              {origin && `from ${formatShortDate(todo.day)}`}
            </span>
          )}
        </span>
      </label>
      {children}
    </li>
  );
}
