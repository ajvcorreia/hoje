import { useEffect, useState, type FormEvent } from 'react';
import type { Event as HojeEvent } from '../../api/types';
import { btnDanger, btnPrimary, btnSecondary, inputClass } from '../../components/ui/classes';
import { Dialog } from '../../components/ui/Dialog';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { formatDayHeading, todayIso } from '../../lib/dates';
import { useCategories, useDefaultCategoryId } from '../categories/api';
import { CategorySwatch } from '../categories/CategorySwatch';
import { getClientId } from '../../api/clientId';
import { subscribeChanges } from '../realtime/store';
import { conflictCurrent, useCreateEvent, useDeleteEvent, useEvent, useUpdateEvent } from './api';
import {
  blankForm,
  formFromEvent,
  toCreateBody,
  toUpdatePatch,
  validateForm,
  type EventFormState,
  type ReminderChoice,
  type ReminderUnit,
} from './eventForm';

export interface EventEditorProps {
  mode: 'create' | 'edit';
  /** Required in `edit` mode. */
  eventId?: string;
  /** ISO date preselected in `create` mode (defaults to today). */
  initialDate?: string;
  /** Called after save, delete or cancel. */
  onClose(): void;
  /** `dialog` (default, centred modal) or `sheet` (full-screen, for phones). */
  variant?: 'dialog' | 'sheet';
}

/**
 * Create / edit form for one event. Title (autofocused, Enter saves) and category are always
 * visible; dates, times, reminder, repeat and notes sit under a collapsed "More" section.
 * Editing sends the event's `version`; if the event changed elsewhere the form offers to
 * reload the server's copy or overwrite it.
 */
export function EventEditor({
  mode,
  eventId,
  initialDate,
  onClose,
  variant = 'dialog',
}: EventEditorProps) {
  const title = mode === 'create' ? 'New event' : 'Edit event';
  const existing = useEvent(mode === 'edit' ? eventId : undefined);
  return (
    <Dialog title={title} onClose={onClose} variant={variant}>
      {mode === 'create' ? (
        <EditorForm mode="create" initialDate={initialDate ?? todayIso()} onClose={onClose} />
      ) : existing.isPending ? (
        <p className="text-sm text-text-muted">Loading...</p>
      ) : existing.isError ? (
        <div className="space-y-3">
          <FormError message={describeError(existing.error)} />
          <button type="button" className={btnSecondary} onClick={onClose}>
            Close
          </button>
        </div>
      ) : (
        <EditorForm
          mode="edit"
          event={existing.data}
          onClose={onClose}
          refetchEvent={async () => (await existing.refetch()).data}
        />
      )}
    </Dialog>
  );
}

type FormProps =
  | { mode: 'create'; initialDate: string; onClose(): void }
  | {
      mode: 'edit';
      event: HojeEvent;
      onClose(): void;
      refetchEvent(): Promise<HojeEvent | undefined>;
    };

function EditorForm(props: FormProps) {
  const { onClose } = props;
  const editing = props.mode === 'edit' ? props.event : null;
  const { data: categories } = useCategories();
  const defaultCategoryId = useDefaultCategoryId();
  const create = useCreateEvent();
  const update = useUpdateEvent();
  const remove = useDeleteEvent();

  const [form, setForm] = useState<EventFormState>(() =>
    props.mode === 'edit' ? formFromEvent(props.event) : blankForm(props.initialDate),
  );
  const [version, setVersion] = useState(editing?.version ?? 0);
  const [moreOpen, setMoreOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<HojeEvent | null>(null);
  const [busy, setBusy] = useState(false);
  const [remote, setRemote] = useState<{ op: 'update' | 'delete' } | null>(null);

  // Another device changed (or deleted) this event while the editor is open.
  const editingId = editing?.id;
  useEffect(() => {
    if (!editingId) return;
    return subscribeChanges((change) => {
      if (change.entity !== 'event' || change.id !== editingId) return;
      if (change.client_id === getClientId()) return;
      if (change.op === 'delete') setRemote({ op: 'delete' });
      else if (change.version > version) setRemote({ op: 'update' });
    });
  }, [editingId, version]);

  const loadLatest = async () => {
    if (props.mode !== 'edit') return;
    const latest = await props.refetchEvent();
    if (!latest) return;
    setForm(formFromEvent(latest));
    setVersion(latest.version);
    setRemote(null);
    setConflict(null);
    setError(null);
  };

  const set = <K extends keyof EventFormState>(key: K, value: EventFormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const categoryId = form.categoryId || defaultCategoryId || '';
  const selectedCategory = categories?.find((c) => c.id === categoryId);

  const onStartDate = (value: string) =>
    setForm((f) => ({
      ...f,
      startDate: value,
      // Keep a single-day event single-day, and never leave the end before the start.
      endDate: f.endDate === f.startDate || f.endDate < value ? value : f.endDate,
    }));

  const save = async (baseVersion: number) => {
    const problem = validateForm(form);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      if (editing) {
        await update.mutateAsync({
          id: editing.id,
          version: baseVersion,
          patch: toUpdatePatch({ ...form, categoryId }),
        });
      } else {
        await create.mutateAsync(toCreateBody(form));
      }
      onClose();
    } catch (e) {
      const current = conflictCurrent(e);
      if (current) setConflict(current);
      else setError(describeError(e));
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!busy && !conflict) void save(version);
  };

  const reload = () => {
    if (!conflict) return;
    setForm(formFromEvent(conflict));
    setVersion(conflict.version);
    setConflict(null);
    setError(null);
  };

  const overwrite = () => {
    if (!conflict) return;
    const base = conflict.version;
    setVersion(base);
    setConflict(null);
    void save(base);
  };

  const onDelete = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      await remove.mutateAsync(editing.id);
      onClose();
    } catch (e) {
      setError(describeError(e));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-3" noValidate>
      <Field
        label="Title"
        data-autofocus
        value={form.title}
        onChange={(e) => set('title', e.target.value)}
        maxLength={200}
        autoComplete="off"
      />

      <div className="space-y-1">
        <label htmlFor="event-category" className="block text-sm font-medium">
          Category
        </label>
        <div className="flex items-center gap-2">
          <CategorySwatch colour={selectedCategory?.colour} className="size-4" />
          <select
            id="event-category"
            value={categoryId}
            onChange={(e) => set('categoryId', e.target.value)}
            className={inputClass}
          >
            {categoryId === '' ? <option value="">Choose a category</option> : null}
            {categories?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p className="text-sm text-text-muted">{formatDayHeading(form.startDate)}</p>

      <div>
        <button
          type="button"
          aria-expanded={moreOpen}
          aria-controls="event-more"
          onClick={() => setMoreOpen((open) => !open)}
          className="inline-flex min-h-9 items-center gap-1 rounded-md text-sm font-medium text-accent hover:underline"
        >
          <span aria-hidden="true">{moreOpen ? '▾' : '▸'}</span>
          More
        </button>
        {moreOpen ? (
          <div id="event-more" className="mt-2 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field
                label="Start date"
                type="date"
                value={form.startDate}
                onChange={(e) => onStartDate(e.target.value)}
              />
              <Field
                label="End date"
                type="date"
                value={form.endDate}
                min={form.startDate}
                onChange={(e) => set('endDate', e.target.value)}
              />
            </div>
            <label className="flex min-h-9 items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.allDay}
                onChange={(e) => set('allDay', e.target.checked)}
                className="size-4"
              />
              All day
            </label>
            {form.allDay ? null : (
              <div className="grid grid-cols-2 gap-3">
                <Field
                  label="Start time"
                  type="time"
                  value={form.startTime}
                  onChange={(e) => set('startTime', e.target.value)}
                />
                <Field
                  label="End time"
                  type="time"
                  value={form.endTime}
                  onChange={(e) => set('endTime', e.target.value)}
                />
              </div>
            )}

            <div className="space-y-1">
              <label htmlFor="event-reminder" className="block text-sm font-medium">
                Reminder
              </label>
              <select
                id="event-reminder"
                value={form.reminder}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    reminder: e.target.value as ReminderChoice,
                    reminderTouched: true,
                  }))
                }
                className={inputClass}
              >
                <option value="none">None</option>
                <option value="1440">1 day before</option>
                <option value="10080">1 week before</option>
                <option value="custom">Custom…</option>
              </select>
              {form.reminder === 'custom' ? (
                <div className="flex items-end gap-2">
                  <Field
                    label="Remind me"
                    type="number"
                    min={0}
                    inputMode="numeric"
                    value={form.customAmount}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        customAmount: e.target.value,
                        reminderTouched: true,
                      }))
                    }
                  />
                  <div className="space-y-1">
                    <label htmlFor="event-reminder-unit" className="sr-only">
                      Reminder unit
                    </label>
                    <select
                      id="event-reminder-unit"
                      value={form.customUnit}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          customUnit: e.target.value as ReminderUnit,
                          reminderTouched: true,
                        }))
                      }
                      className={inputClass}
                    >
                      <option value="minutes">minutes</option>
                      <option value="hours">hours</option>
                      <option value="days">days</option>
                    </select>
                  </div>
                  <span className="pb-2.5 text-sm text-text-muted">before</span>
                </div>
              ) : null}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label htmlFor="event-repeat" className="block text-sm font-medium">
                  Repeat
                </label>
                <select
                  id="event-repeat"
                  value={form.repeat}
                  onChange={(e) => set('repeat', e.target.value as EventFormState['repeat'])}
                  className={inputClass}
                >
                  <option value="none">None</option>
                  <option value="monthly">Monthly</option>
                  <option value="yearly">Yearly</option>
                </select>
              </div>
              {form.repeat === 'none' ? null : (
                <Field
                  label="Until (optional)"
                  type="date"
                  value={form.repeatUntil}
                  min={form.startDate}
                  onChange={(e) => set('repeatUntil', e.target.value)}
                />
              )}
            </div>

            <div className="space-y-1">
              <label htmlFor="event-notes" className="block text-sm font-medium">
                Notes
              </label>
              <textarea
                id="event-notes"
                value={form.notes}
                onChange={(e) => set('notes', e.target.value)}
                rows={3}
                maxLength={5000}
                className={`${inputClass} py-2`}
              />
            </div>
          </div>
        ) : null}
      </div>

      {remote ? (
        <div
          role="alert"
          className="space-y-2 rounded-md border border-border bg-surface-muted p-3 text-sm"
        >
          <p className="font-medium">
            {remote.op === 'delete'
              ? 'This event was deleted on another device.'
              : 'This event was changed on another device.'}
          </p>
          <div className="flex gap-2">
            {remote.op === 'delete' ? (
              <button type="button" className={btnPrimary} onClick={onClose}>
                Close
              </button>
            ) : (
              <>
                <button type="button" className={btnPrimary} onClick={() => void loadLatest()}>
                  Load latest
                </button>
                <button type="button" className={btnSecondary} onClick={() => setRemote(null)}>
                  Keep editing
                </button>
              </>
            )}
          </div>
        </div>
      ) : null}

      {conflict ? (
        <div
          role="alert"
          className="space-y-2 rounded-md border border-border bg-surface-muted p-3 text-sm"
        >
          <p className="font-medium">This event was changed elsewhere.</p>
          <p className="text-text-muted">
            Reload to see the latest version (your edits are discarded), or overwrite it with yours.
          </p>
          <div className="flex gap-2">
            <button type="button" className={btnSecondary} onClick={reload}>
              Reload
            </button>
            <button type="button" className={btnPrimary} onClick={overwrite}>
              Overwrite
            </button>
          </div>
        </div>
      ) : null}

      <FormError message={error} />

      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" className={btnPrimary} disabled={busy || conflict !== null}>
          Save
        </button>
        <button type="button" className={btnSecondary} onClick={onClose}>
          Cancel
        </button>
        {editing ? (
          <button
            type="button"
            className={`${btnDanger} ml-auto`}
            disabled={busy}
            onClick={() => void onDelete()}
          >
            Delete
          </button>
        ) : null}
      </div>
    </form>
  );
}
