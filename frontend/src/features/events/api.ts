import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type QueryKey,
} from '@tanstack/react-query';
import { api, ApiError, unwrap } from '../../api/client';
import type {
  Event as HojeEvent,
  EventConflict,
  EventCreate,
  EventUpdate,
  Occurrence,
} from '../../api/types';
import { AUTH_STATE_KEY } from '../../app/useAuthState';
import { useToast } from '../../components/ui/useToast';
import { useDefaultCategoryId } from '../categories/api';
import { LEAVE_KEY } from '../leave/api';

/** Root of every occurrences query key: `['occurrences', from, to, ...categoryIds]`. */
export const OCCURRENCES_KEY = ['occurrences'] as const;
export const eventKey = (id: string) => ['event', id] as const;

/** After any event write: refetch the occurrences and the vacation balance. */
function refreshEvents(qc: QueryClient) {
  void qc.invalidateQueries({ queryKey: LEAVE_KEY });
  return qc.invalidateQueries({ queryKey: OCCURRENCES_KEY });
}

/**
 * Occurrences (expanded repeats) overlapping `[from, to]` (inclusive ISO dates).
 * The desktop grid asks for the whole selected year in one call; mobile asks per month.
 * `categoryIds` narrows server-side; leave it out to get everything (hidden categories
 * are filtered by the views).
 */
export function occurrencesQuery(from: string, to: string, categoryIds?: readonly string[]) {
  return queryOptions({
    queryKey: [...OCCURRENCES_KEY, from, to, ...(categoryIds ?? [])] as const,
    queryFn: async () => {
      const result = unwrap(
        await api.GET('/api/v1/events', {
          params: {
            query: { from, to, category_ids: categoryIds?.length ? [...categoryIds] : undefined },
          },
        }),
      );
      return result.occurrences;
    },
  });
}

/** With `keepPrevious` the last range stays on screen while a new one loads (mobile paging). */
export function useOccurrences(
  from: string,
  to: string,
  categoryIds?: readonly string[],
  options?: { keepPrevious?: boolean },
) {
  return useQuery({
    ...occurrencesQuery(from, to, categoryIds),
    placeholderData: options?.keepPrevious ? keepPreviousData : undefined,
  });
}

/** One event by id (for the editor). Disabled while `id` is undefined. */
export function useEvent(id: string | undefined) {
  return useQuery({
    queryKey: eventKey(id ?? ''),
    enabled: id !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/events/{event_id}', {
          params: { path: { event_id: id ?? '' } },
        }),
      ),
  });
}

/** Title search (`GET /events/search`). Disabled until `q` has at least 2 characters. */
export function useSearchEvents(q: string, categoryIds?: readonly string[]) {
  const term = q.trim();
  return useQuery({
    queryKey: ['events', 'search', term, ...(categoryIds ?? [])] as const,
    enabled: term.length >= 2,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/events/search', {
          params: {
            query: {
              q: term,
              limit: 8,
              category_ids: categoryIds?.length ? [...categoryIds] : undefined,
            },
          },
        }),
      ),
  });
}

type Snapshot = [QueryKey, Occurrence[] | undefined][];

/** Applies `fn` to every cached occurrences list; returns the previous values for rollback. */
function patchOccurrenceCaches(
  qc: QueryClient,
  fn: (list: Occurrence[], from: string, to: string) => Occurrence[],
): Snapshot {
  const snapshot = qc.getQueriesData<Occurrence[]>({ queryKey: OCCURRENCES_KEY });
  for (const [key, data] of snapshot) {
    if (!data) continue;
    qc.setQueryData<Occurrence[]>(key, fn(data, String(key[1]), String(key[2])));
  }
  return snapshot;
}

function rollback(qc: QueryClient, snapshot: Snapshot | undefined) {
  for (const [key, data] of snapshot ?? []) qc.setQueryData(key, data);
}

/** Remember the category used last, as the server does, so the next editor preselects it. */
function rememberCategory(qc: QueryClient, categoryId: string) {
  qc.setQueryData<{ user?: { last_category_id?: string | null } | null } | undefined>(
    AUTH_STATE_KEY,
    (state) =>
      state?.user ? { ...state, user: { ...state.user, last_category_id: categoryId } } : state,
  );
}

let tempCounter = 0;

/** Body of a new event: the server defaults (all-day, no repeat, no reminders) may be omitted. */
export type NewEvent = Omit<EventCreate, 'all_day' | 'reminders' | 'repeat' | 'label_vertical'> &
  Partial<Pick<EventCreate, 'all_day' | 'reminders' | 'repeat' | 'label_vertical'>>;

/**
 * `POST /events`. Optimistically inserts the new (non-repeating) event into every cached
 * occurrences range it falls in; the list is refetched afterwards to pick up server values.
 */
export function useCreateEvent() {
  const qc = useQueryClient();
  const defaultCategoryId = useDefaultCategoryId();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: NewEvent) =>
      unwrap(await api.POST('/api/v1/events', { body: body as EventCreate })),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: OCCURRENCES_KEY });
      const end = body.end_date ?? body.start_date;
      const now = new Date().toISOString();
      tempCounter += 1;
      const temp: HojeEvent = {
        id: `00000000-0000-0000-0000-${String(tempCounter).padStart(12, '0')}`,
        category_id: body.category_id ?? defaultCategoryId ?? '',
        title: body.title,
        notes: body.notes ?? null,
        start_date: body.start_date,
        end_date: end,
        all_day: body.all_day ?? true,
        start_time: body.start_time ?? null,
        end_time: body.end_time ?? null,
        timezone: body.timezone ?? 'UTC',
        repeat: body.repeat ?? 'none',
        repeat_until: body.repeat_until ?? null,
        counts_as_leave: false,
        label_vertical: body.label_vertical ?? false,
        day_order: 0,
        reminders: body.reminders ?? [],
        version: 1,
        created_at: now,
        updated_at: now,
      };
      const occurrence: Occurrence = {
        event_id: temp.id,
        occurrence_start: temp.start_date,
        occurrence_end: temp.end_date,
        event: temp,
      };
      const snapshot =
        (body.repeat ?? 'none') === 'none'
          ? patchOccurrenceCaches(qc, (list, from, to) =>
              temp.start_date <= to && temp.end_date >= from ? [...list, occurrence] : list,
            )
          : undefined;
      return { snapshot };
    },
    onError: (_error, _vars, context) => rollback(qc, context?.snapshot),
    onSuccess: ({ event }) => {
      qc.setQueryData(eventKey(event.id), event);
      rememberCategory(qc, event.category_id);
    },
    onSettled: () => refreshEvents(qc),
  });
}

export interface UpdateEventVariables {
  id: string;
  /** The `version` the edit was based on; the server answers 409 if it moved on. */
  version: number;
  patch: Omit<EventUpdate, 'version'>;
}

/**
 * `PATCH /events/{id}` with the optimistic-concurrency `version`. On a version mismatch the
 * mutation fails with an `ApiError` (status 409); use {@link conflictCurrent} to read the
 * server's current event from it.
 */
export function useUpdateEvent() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async ({ id, version, patch }: UpdateEventVariables) =>
      unwrap(
        await api.PATCH('/api/v1/events/{event_id}', {
          params: { path: { event_id: id } },
          body: { ...patch, version },
        }),
      ),
    onSuccess: ({ event }) => {
      qc.setQueryData(eventKey(event.id), event);
      rememberCategory(qc, event.category_id);
    },
    onSettled: () => refreshEvents(qc),
  });
}

/** `POST /events/{id}/restore` (undo of a delete). */
export function useRestoreEvent() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST('/api/v1/events/{event_id}/restore', {
          params: { path: { event_id: id } },
        }),
      ),
    onSettled: () => refreshEvents(qc),
  });
}

/** Milliseconds the "Event deleted · Undo" toast stays up. */
export const UNDO_WINDOW_MS = 8000;

/**
 * `DELETE /events/{id}` (soft delete). The event disappears from the caches immediately and
 * a toast "Event deleted · Undo" is shown for 8 s; Undo calls the restore endpoint.
 */
export function useDeleteEvent() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (id: string) => {
      unwrap(
        await api.DELETE('/api/v1/events/{event_id}', {
          params: { path: { event_id: id } },
        }),
      );
    },
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: OCCURRENCES_KEY });
      return {
        snapshot: patchOccurrenceCaches(qc, (list) => list.filter((o) => o.event_id !== id)),
      };
    },
    onError: (_error, _id, context) => rollback(qc, context?.snapshot),
    onSuccess: (_data, id) => {
      toast.show({
        message: 'Event deleted',
        actionLabel: 'Undo',
        durationMs: UNDO_WINDOW_MS,
        onAction: () => {
          void (async () => {
            try {
              unwrap(
                await api.POST('/api/v1/events/{event_id}/restore', {
                  params: { path: { event_id: id } },
                }),
              );
            } catch {
              toast.show({ message: 'Could not restore the event' });
            } finally {
              void qc.invalidateQueries({ queryKey: OCCURRENCES_KEY });
            }
          })();
        },
      });
    },
    onSettled: () => refreshEvents(qc),
  });
}

/** The server's current event from a 409 conflict, or null for any other error. */
export function conflictCurrent(error: unknown): HojeEvent | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const current = (error.body as Partial<EventConflict>).current;
  return current ?? null;
}

/**
 * `POST /events/reorder`: the ids of the events listed for one day, in their new order. Each
 * event gets position 1..n (one position per event, shared by all the days it covers). The
 * order is applied to every cached occurrences list at once so the grid and the popover follow
 * immediately; a failure restores the previous lists and says so.
 */
export function useReorderEvents() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (ids: string[]) => {
      unwrap(await api.POST('/api/v1/events/reorder', { body: { ids } }));
    },
    onMutate: async (ids) => {
      await qc.cancelQueries({ queryKey: OCCURRENCES_KEY });
      const position = new Map(ids.map((id, index) => [id, index + 1]));
      return {
        snapshot: patchOccurrenceCaches(qc, (list) =>
          list.map((o) => {
            const day_order = position.get(o.event_id);
            return day_order === undefined ? o : { ...o, event: { ...o.event, day_order } };
          }),
        ),
      };
    },
    onError: (_error, _ids, context) => {
      rollback(qc, context?.snapshot);
      toast.show({ message: 'Could not reorder the events' });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: OCCURRENCES_KEY }),
  });
}
