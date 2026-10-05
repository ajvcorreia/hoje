import type { QueryKey } from '@tanstack/react-query';

export type RealtimeEntity =
  | 'event'
  | 'category'
  | 'leave_policy'
  | 'holiday'
  | 'holiday_calendar'
  | 'user'
  | 'backup_run'
  | 'data'
  | 'birthday';

export interface ChangeMessage {
  entity: RealtimeEntity;
  op: 'create' | 'update' | 'delete';
  id: string;
  version: number;
  client_id: string | null;
}

/**
 * Which cached queries a remote change makes stale. Keys: `['leave', ...]` (balances,
 * previews), `['holidays', ...]` (overlays and per-calendar lists), `['holiday-calendars']`.
 */
const KEYS: Record<RealtimeEntity, (c: ChangeMessage) => QueryKey[]> = {
  event: (c) => [
    ['occurrences'],
    ['events', 'search'],
    ['leave'],
    // A deleted event's editor keeps its last copy so it can show the "deleted" notice.
    ...(c.op === 'delete' ? [] : [['event', c.id] as QueryKey]),
  ],
  // Colours, hidden and leave flags change how occurrences render.
  category: () => [['categories'], ['occurrences'], ['leave']],
  user: () => [['auth', 'state'], ['me'], ['occurrences']],
  leave_policy: () => [['leave']],
  holiday: () => [['holidays'], ['holiday-calendars'], ['leave']],
  holiday_calendar: () => [['holidays'], ['holiday-calendars'], ['leave']],
  // Backup runs change status in the worker: refresh Settings > Backups (owner only).
  backup_run: () => [['backups']],
  // A FelizAnniv sync or connection change: the overlay and Settings › FelizAnniv birthdays.
  birthday: () => [['birthdays'], ['integrations', 'felizanniv']],
  // An import rewrites everything the user has: an empty key prefix invalidates every query.
  data: () => [[]],
};

export function keysForChange(change: ChangeMessage): QueryKey[] {
  return KEYS[change.entity]?.(change) ?? [];
}
