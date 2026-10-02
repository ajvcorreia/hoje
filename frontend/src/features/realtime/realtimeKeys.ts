import type { QueryKey } from '@tanstack/react-query';

export type RealtimeEntity =
  'event' | 'category' | 'leave_policy' | 'holiday' | 'holiday_calendar' | 'user';

export interface ChangeMessage {
  entity: RealtimeEntity;
  op: 'create' | 'update' | 'delete';
  id: string;
  version: number;
  client_id: string | null;
}

/**
 * Which cached queries a remote change makes stale. Phase 5 fills in the leave / holiday
 * entries with its own keys; unknown prefixes are harmless (nothing matches).
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
  holiday: () => [['holidays'], ['leave']],
  holiday_calendar: () => [['holidays'], ['leave']],
};

export function keysForChange(change: ChangeMessage): QueryKey[] {
  return KEYS[change.entity]?.(change) ?? [];
}
