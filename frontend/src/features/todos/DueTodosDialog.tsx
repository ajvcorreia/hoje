import { useState } from 'react';
import { Dialog } from '../../components/ui/Dialog';
import { btnPrimary } from '../../components/ui/classes';
import { useDueTodos } from './api';
import { TodoCheck } from './TodoItem';

/**
 * Pop-up shown once per page load (including a refresh) when open to-dos are due today or
 * overdue. They can be checked off right in it. It is decided from the first answer only, so a
 * to-do that becomes due later (another tab, live sync) never opens it by surprise.
 */
export function DueTodosDialog() {
  const { data: todos } = useDueTodos();
  const [decided, setDecided] = useState<boolean | null>(null);
  const [closed, setClosed] = useState(false);
  if (decided === null && todos) setDecided(todos.length > 0);
  if (!decided || closed || !todos || todos.length === 0) return null;
  return (
    <Dialog title="To-dos due" onClose={() => setClosed(true)}>
      <p className="mb-2 text-sm text-text-muted">
        These are due today or already overdue. Check them off as you finish them.
      </p>
      <ul aria-label="To-dos due" className="space-y-0.5">
        {todos.map((todo) => (
          <TodoCheck key={todo.id} todo={todo} />
        ))}
      </ul>
      <div className="mt-4 flex justify-end">
        <button type="button" data-autofocus className={btnPrimary} onClick={() => setClosed(true)}>
          Close
        </button>
      </div>
    </Dialog>
  );
}
