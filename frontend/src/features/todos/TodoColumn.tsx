import { useState, type FormEvent } from 'react';
import type { Todo } from '../../api/types';
import { Dialog } from '../../components/ui/Dialog';
import { btnPrimary, btnSecondary, inputClass } from '../../components/ui/classes';
import { useToast } from '../../components/ui/useToast';
import { formatDayHeading } from '../../lib/dates';
import { describeError } from '../../lib/errors';
import { useCreateTodo, useDoneTodos, useOpenTodos } from './api';
import { TodoCheck } from './TodoItem';
import { TodoRow } from './TodoSection';

interface TodoColumnProps {
  /** Today (ISO), which splits the due dates. */
  today: string;
}

/** The open to-dos split by due date: none, today (or overdue) and later. */
function splitTodos(todos: readonly Todo[], today: string) {
  const none: Todo[] = [];
  const now: Todo[] = [];
  const later: Todo[] = [];
  for (const todo of todos) {
    if (!todo.due_date) none.push(todo);
    else if (todo.due_date <= today) now.push(todo);
    else later.push(todo);
  }
  const byDue = (a: Todo, b: Todo) => (a.due_date ?? '').localeCompare(b.due_date ?? '');
  return { none, now: now.sort(byDue), later: later.sort(byDue) };
}

/**
 * Every open to-do beside the calendar, in three sections (no due date, due today or overdue,
 * due later), with a field to add one and a Done button listing the ones already checked off.
 */
export function TodoColumn({ today }: TodoColumnProps) {
  const { data: todos } = useOpenTodos();
  const [editing, setEditing] = useState<string | null>(null);
  const [showDone, setShowDone] = useState(false);
  const { none, now, later } = splitTodos(todos ?? [], today);

  const section = (title: string, list: Todo[]) =>
    list.length > 0 ? (
      <section aria-label={title} className="space-y-0.5">
        <h3 className="flex items-baseline justify-between px-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
          {title}
          <span className="tabular-nums">{list.length}</span>
        </h3>
        <ul className="space-y-0.5">
          {list.map((todo) => (
            <TodoRow
              key={todo.id}
              todo={todo}
              idPrefix="todo-column"
              editing={editing === todo.id}
              onEdit={() => setEditing(todo.id)}
              onClose={() => setEditing(null)}
            />
          ))}
        </ul>
      </section>
    ) : null;

  return (
    <aside
      aria-label="To-do list"
      className="flex max-h-full w-72 shrink-0 flex-col gap-3 self-start overflow-y-auto rounded-lg border border-border bg-surface p-2"
    >
      <div className="flex items-center justify-between gap-2 px-2">
        <h2 className="text-sm font-semibold">To-dos</h2>
        <button type="button" className={btnSecondary} onClick={() => setShowDone(true)}>
          Done
        </button>
      </div>
      <AddTodo />
      {todos && todos.length === 0 ? (
        <p className="px-2 text-sm text-text-muted">Nothing to do.</p>
      ) : null}
      {section('No due date', none)}
      {section('Due today', now)}
      {section('Due later', later)}
      {showDone ? <DoneTodosDialog onClose={() => setShowDone(false)} /> : null}
    </aside>
  );
}

/** A title and an optional due date; the to-do is placed on today. */
function AddTodo() {
  const create = useCreateTodo();
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    create
      .mutateAsync({ title: trimmed, due_date: due || null })
      .catch((error: unknown) =>
        toast.show({ message: `Could not add the to-do. ${describeError(error)}` }),
      );
    setTitle('');
    setDue('');
  };
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2 px-1">
      <label htmlFor="todo-column-title" className="sr-only">
        Add a to-do
      </label>
      <input
        id="todo-column-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Add a to-do…"
        autoComplete="off"
        maxLength={200}
        className={`${inputClass} w-full`}
      />
      <label htmlFor="todo-column-due" className="sr-only">
        Due date (optional)
      </label>
      <input
        id="todo-column-due"
        type="date"
        value={due}
        min="1900-01-01"
        max="2200-12-31"
        onChange={(e) => setDue(e.target.value)}
        title="Due date (optional)"
        className={`${inputClass} w-auto min-w-0 flex-1`}
      />
      <button type="submit" className={btnSecondary}>
        Add
      </button>
    </form>
  );
}

/** The checked-off to-dos, grouped by the day they were done, most recent first. */
export function DoneTodosDialog({ onClose }: { onClose: () => void }) {
  const { data: todos, isPending } = useDoneTodos();
  const groups: { day: string; todos: Todo[] }[] = [];
  for (const todo of todos ?? []) {
    const day = todo.completed_on ?? '';
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.todos.push(todo);
    else groups.push({ day, todos: [todo] });
  }
  return (
    <Dialog title="Done to-dos" onClose={onClose}>
      {isPending ? (
        <p className="text-sm text-text-muted">Loading…</p>
      ) : groups.length === 0 ? (
        <p className="text-sm text-text-muted">Nothing done yet.</p>
      ) : (
        <div className="max-h-[60vh] space-y-3 overflow-y-auto">
          {groups.map((group) => (
            <section key={group.day} aria-label={`Done on ${group.day}`}>
              <h3 className="px-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
                {group.day ? formatDayHeading(group.day) : ''}
              </h3>
              <ul className="space-y-0.5">
                {group.todos.map((todo) => (
                  <TodoCheck key={todo.id} todo={todo} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      <p className="mt-3 text-xs text-text-muted">Untick one to put it back on the list.</p>
      <div className="mt-4 flex justify-end">
        <button type="button" data-autofocus className={btnPrimary} onClick={onClose}>
          Close
        </button>
      </div>
    </Dialog>
  );
}
