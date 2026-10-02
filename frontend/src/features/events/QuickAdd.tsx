import { useState, type FormEvent } from 'react';
import { inputClass } from '../../components/ui/classes';
import { useToast } from '../../components/ui/useToast';
import { describeError } from '../../lib/errors';
import { useCreateEvent } from './api';

interface QuickAddProps {
  /** ISO date the event is created on. */
  date: string;
  /** Called after the event was sent (the list updates optimistically). */
  onCreated?(): void;
}

/**
 * The type-to-add field: type a title and press Enter to create an all-day event on
 * `date`. The category is omitted so the server applies the user's last used one.
 * The input carries `data-autofocus` so popovers and dialogs focus it immediately.
 * A failure is reported with a toast, since the host (a popover) usually closes right away.
 */
export function QuickAdd({ date, onCreated }: QuickAddProps) {
  const [title, setTitle] = useState('');
  const create = useCreateEvent();
  const toast = useToast();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    create
      .mutateAsync({ title: trimmed, start_date: date, end_date: date, all_day: true })
      .catch((error: unknown) =>
        toast.show({ message: `Could not add the event. ${describeError(error)}` }),
      );
    setTitle('');
    onCreated?.();
  };

  return (
    <form onSubmit={submit}>
      <label htmlFor={`quick-add-${date}`} className="sr-only">
        Add an event
      </label>
      <input
        id={`quick-add-${date}`}
        data-autofocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Add an event…"
        autoComplete="off"
        maxLength={200}
        className={inputClass}
      />
    </form>
  );
}
