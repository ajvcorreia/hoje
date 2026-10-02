import type { Event as HojeEvent, EventUpdate } from '../../api/types';
import type { NewEvent } from './api';

/** Reminder choices offered in the editor; `custom` reveals a number + unit. */
export type ReminderChoice = 'none' | '1440' | '10080' | 'custom';
export type ReminderUnit = 'minutes' | 'hours' | 'days';

export const UNIT_MINUTES: Record<ReminderUnit, number> = { minutes: 1, hours: 60, days: 1440 };

/** Editable state of the event form. Dates are ISO strings, times `HH:mm`. */
export interface EventFormState {
  title: string;
  /** '' = untouched: create omits it so the server applies the last used category. */
  categoryId: string;
  startDate: string;
  endDate: string;
  allDay: boolean;
  startTime: string;
  endTime: string;
  reminder: ReminderChoice;
  customAmount: string;
  customUnit: ReminderUnit;
  /** True once the user changed the reminder: only then are reminders sent on edit. */
  reminderTouched: boolean;
  repeat: 'none' | 'monthly' | 'yearly';
  repeatUntil: string;
  notes: string;
}

export function blankForm(date: string): EventFormState {
  return {
    title: '',
    categoryId: '',
    startDate: date,
    endDate: date,
    allDay: true,
    startTime: '',
    endTime: '',
    reminder: 'none',
    customAmount: '1',
    customUnit: 'days',
    reminderTouched: false,
    repeat: 'none',
    repeatUntil: '',
    notes: '',
  };
}

/** Splits a minute offset into the largest whole unit. */
export function splitOffset(minutes: number): { amount: number; unit: ReminderUnit } {
  if (minutes > 0 && minutes % 1440 === 0) return { amount: minutes / 1440, unit: 'days' };
  if (minutes > 0 && minutes % 60 === 0) return { amount: minutes / 60, unit: 'hours' };
  return { amount: minutes, unit: 'minutes' };
}

export function formFromEvent(event: HojeEvent): EventFormState {
  const first = event.reminders[0]?.offset_minutes;
  let reminder: ReminderChoice = 'none';
  let customAmount = '1';
  let customUnit: ReminderUnit = 'days';
  if (first !== undefined) {
    if (first === 1440) reminder = '1440';
    else if (first === 10080) reminder = '10080';
    else {
      reminder = 'custom';
      const split = splitOffset(first);
      customAmount = String(split.amount);
      customUnit = split.unit;
    }
  }
  return {
    title: event.title,
    categoryId: event.category_id,
    startDate: event.start_date,
    endDate: event.end_date,
    allDay: event.all_day,
    startTime: event.start_time?.slice(0, 5) ?? '',
    endTime: event.end_time?.slice(0, 5) ?? '',
    reminder,
    customAmount,
    customUnit,
    reminderTouched: false,
    repeat: event.repeat,
    repeatUntil: event.repeat_until ?? '',
    notes: event.notes ?? '',
  };
}

/** Reminder offsets (minutes) for the form; `null` when the custom value is invalid. */
export function reminderOffsets(form: EventFormState): number[] | null {
  switch (form.reminder) {
    case 'none':
      return [];
    case '1440':
      return [1440];
    case '10080':
      return [10080];
    case 'custom': {
      const amount = Number(form.customAmount);
      if (!Number.isInteger(amount) || amount < 0) return null;
      return [amount * UNIT_MINUTES[form.customUnit]];
    }
  }
}

/** First problem with the form as a sentence, or null when it can be saved. */
export function validateForm(form: EventFormState): string | null {
  if (!form.title.trim()) return 'Enter a title.';
  if (!form.startDate) return 'Choose a start date.';
  if (form.endDate && form.endDate < form.startDate)
    return 'The end date is before the start date.';
  if (!form.allDay) {
    if (!form.startTime) return 'Choose a start time, or switch on All day.';
    if (form.endTime && form.endDate === form.startDate && form.endTime < form.startTime) {
      return 'The end time is before the start time.';
    }
  }
  if (form.repeat !== 'none' && form.repeatUntil && form.repeatUntil < form.startDate) {
    return 'Repeat until is before the start date.';
  }
  if (reminderOffsets(form) === null) return 'Enter a whole number for the reminder.';
  return null;
}

function common(form: EventFormState) {
  return {
    title: form.title.trim(),
    start_date: form.startDate,
    end_date: form.endDate || form.startDate,
    all_day: form.allDay,
    start_time: form.allDay ? null : form.startTime || null,
    end_time: form.allDay ? null : form.endTime || null,
    repeat: form.repeat,
    repeat_until: form.repeat === 'none' ? null : form.repeatUntil || null,
    notes: form.notes.trim() ? form.notes : null,
  };
}

/** Body for `POST /events`. */
export function toCreateBody(form: EventFormState): NewEvent {
  const body: NewEvent = {
    ...common(form),
    reminders: (reminderOffsets(form) ?? []).map((offset_minutes) => ({ offset_minutes })),
  };
  if (form.categoryId) body.category_id = form.categoryId;
  return body;
}

/** Body (minus `version`) for `PATCH /events/{id}`. Reminders are sent only if changed. */
export function toUpdatePatch(form: EventFormState): Omit<EventUpdate, 'version'> {
  const patch: Omit<EventUpdate, 'version'> = { ...common(form), category_id: form.categoryId };
  if (form.reminderTouched) {
    patch.reminders = (reminderOffsets(form) ?? []).map((offset_minutes) => ({ offset_minutes }));
  }
  return patch;
}
