import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import type { Todo, TodoUpdate } from '../../api/types';
import { btnPrimary, btnSecondary, inputClass } from '../../components/ui/classes';
import { useToast } from '../../components/ui/useToast';
import { describeError } from '../../lib/errors';
import { useCreateTodo, useDeleteTodo, useTodos, useUpdateTodo } from './api';
import { TodoCheck } from './TodoItem';

const rowButton =
  'inline-flex min-h-8 min-w-8 shrink-0 items-center justify-center rounded-md text-text-muted hover:bg-surface-muted hover:text-text';

interface TodoSectionProps {
  /** ISO date whose to-dos are listed and on which new ones are placed. */
  date: string;
  /** Prefix for the field ids, so two sections for the same date never clash. */
  idPrefix?: string;
}

/**
 * The to-dos of one day: open ones (carried over from earlier days until checked off), the ones
 * checked off that day, and a field to add another with an optional due date. Each one can be
 * edited in place (title and due date) or deleted.
 */
export function TodoSection({ date, idPrefix = 'todo' }: TodoSectionProps) {
  const { data: todos } = useTodos(date, date);
  const create = useCreateTodo();
  const remove = useDeleteTodo();
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const [editing, setEditing] = useState<string | null>(null);

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
          {todos.map((todo) =>
            editing === todo.id ? (
              <TodoEditor
                key={todo.id}
                todo={todo}
                idPrefix={`${idPrefix}-edit`}
                onClose={() => setEditing(null)}
              />
            ) : (
              <TodoCheck key={todo.id} todo={todo} showOrigin>
                <button
                  type="button"
                  aria-label={`Edit to-do ${todo.title}`}
                  title="Edit"
                  onClick={() => setEditing(todo.id)}
                  className={rowButton}
                >
                  <span aria-hidden="true">✎</span>
                </button>
                <button
                  type="button"
                  aria-label={`Delete to-do ${todo.title}`}
                  title="Delete"
                  onClick={() =>
                    remove.mutate(todo.id, {
                      onError: () => toast.show({ message: 'Could not delete the to-do' }),
                    })
                  }
                  className={rowButton}
                >
                  <span aria-hidden="true">×</span>
                </button>
              </TodoCheck>
            ),
          )}
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

interface TodoEditorProps {
  todo: Todo;
  idPrefix: string;
  onClose: () => void;
}

/** One to-do's title and due date as a small form. Only what changed is sent; Escape cancels. */
function TodoEditor({ todo, idPrefix, onClose }: TodoEditorProps) {
  const update = useUpdateTodo();
  const toast = useToast();
  const [title, setTitle] = useState(todo.title);
  const [due, setDue] = useState(todo.due_date ?? '');
  const titleRef = useRef<HTMLInputElement>(null);
  useEffect(() => titleRef.current?.focus(), []);
  const titleId = `${idPrefix}-title-${todo.id}`;
  const dueId = `${idPrefix}-due-${todo.id}`;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    const patch: TodoUpdate = {};
    if (trimmed !== todo.title) patch.title = trimmed;
    if ((due || null) !== (todo.due_date ?? null)) patch.due_date = due || null;
    if (Object.keys(patch).length > 0) {
      update.mutate(
        { id: todo.id, patch },
        {
          onError: (error) =>
            toast.show({ message: `Could not save the to-do. ${describeError(error)}` }),
        },
      );
    }
    onClose();
  };

  // Escape cancels the edit only, not the popover or dialog around it.
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== 'Escape') return;
    event.stopPropagation();
    onClose();
  };

  return (
    <li>
      <form
        aria-label={`Edit to-do ${todo.title}`}
        onSubmit={submit}
        className="flex flex-wrap items-center gap-2 rounded-md bg-surface-muted p-2"
      >
        <label htmlFor={titleId} className="sr-only">
          To-do
        </label>
        <input
          id={titleId}
          value={title}
          ref={titleRef}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={onKeyDown}
          autoComplete="off"
          maxLength={200}
          className={`${inputClass} min-w-0 flex-1`}
        />
        <label htmlFor={dueId} className="sr-only">
          Due date
        </label>
        <input
          id={dueId}
          type="date"
          value={due}
          min="1900-01-01"
          max="2200-12-31"
          onChange={(e) => setDue(e.target.value)}
          onKeyDown={onKeyDown}
          title="Due date (empty for none)"
          className={`${inputClass} w-auto`}
        />
        <button type="submit" className={btnPrimary}>
          Save
        </button>
        <button type="button" onClick={onClose} className={btnSecondary}>
          Cancel
        </button>
      </form>
    </li>
  );
}
