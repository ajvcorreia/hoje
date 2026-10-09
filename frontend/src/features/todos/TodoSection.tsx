import { useState, type FormEvent } from 'react';
import { btnSecondary, inputClass } from '../../components/ui/classes';
import { useToast } from '../../components/ui/useToast';
import { describeError } from '../../lib/errors';
import { useCreateTodo, useDeleteTodo, useTodos } from './api';
import { TodoCheck } from './TodoItem';

interface TodoSectionProps {
  /** ISO date whose to-dos are listed and on which new ones are placed. */
  date: string;
  /** Prefix for the field ids, so two sections for the same date never clash. */
  idPrefix?: string;
}

/**
 * The to-dos of one day: open ones (carried over from earlier days until checked off), the ones
 * checked off that day, and a field to add another with an optional due date.
 */
export function TodoSection({ date, idPrefix = 'todo' }: TodoSectionProps) {
  const { data: todos } = useTodos(date, date);
  const create = useCreateTodo();
  const remove = useDeleteTodo();
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    create
      .mutateAsync({ title: trimmed, day: date, due_date: due || null })
      .catch((error: unknown) =>
        toast.show({ message: `Could not add the to-do. ${describeError(error)}` }),
      );
    setTitle('');
    setDue('');
  };

  return (
    <section aria-label={`To-dos on ${date}`} className="space-y-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">To-dos</h3>
      {todos && todos.length > 0 && (
        <ul className="space-y-0.5">
          {todos.map((todo) => (
            <TodoCheck key={todo.id} todo={todo} showOrigin>
              <button
                type="button"
                aria-label={`Delete to-do ${todo.title}`}
                onClick={() =>
                  remove.mutate(todo.id, {
                    onError: () => toast.show({ message: 'Could not delete the to-do' }),
                  })
                }
                className="inline-flex min-h-8 min-w-8 shrink-0 items-center justify-center rounded-md text-text-muted hover:bg-surface-muted hover:text-text"
              >
                <span aria-hidden="true">×</span>
              </button>
            </TodoCheck>
          ))}
        </ul>
      )}
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
        <label htmlFor={`${idPrefix}-title-${date}`} className="sr-only">
          Add a to-do
        </label>
        <input
          id={`${idPrefix}-title-${date}`}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Add a to-do…"
          autoComplete="off"
          maxLength={200}
          className={`${inputClass} min-w-0 flex-1`}
        />
        <label htmlFor={`${idPrefix}-due-${date}`} className="sr-only">
          Due date (optional)
        </label>
        <input
          id={`${idPrefix}-due-${date}`}
          type="date"
          value={due}
          min="1900-01-01"
          max="2200-12-31"
          onChange={(e) => setDue(e.target.value)}
          title="Due date (optional)"
          className={`${inputClass} w-auto`}
        />
        <button type="submit" className={btnSecondary}>
          Add
        </button>
      </form>
    </section>
  );
}
