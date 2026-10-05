import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { api, unwrap } from '../../api/client';
import type { BirthdayOccurrence, FelizAnnivStatus } from '../../api/types';
import { useShowBirthdays } from '../../lib/showBirthdays';
import { NO_HOLIDAYS, useHolidayOverlay, type HolidayDay } from '../holidays/api';

/** Root of every birthday overlay query: `['birthdays', from, to]`. */
export const BIRTHDAYS_KEY = ['birthdays'] as const;
export const FELIZANNIV_KEY = ['integrations', 'felizanniv'] as const;

/** Poll the status while a sync is queued or running (fallback for the realtime change). */
const SYNC_POLL_MS = 3000;

/** Connection status of the FelizAnniv integration (the key itself is never sent back). */
export function useFelizAnnivStatus() {
  return useQuery({
    queryKey: FELIZANNIV_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/integrations/felizanniv')),
    refetchInterval: (query) => (query.state.data?.sync_pending ? SYNC_POLL_MS : false),
  });
}

/** `PUT /integrations/felizanniv`: the server tests the connection before saving. */
export function useConnectFelizAnniv() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: { base_url: string; api_key?: string }) =>
      unwrap(await api.PUT('/api/v1/integrations/felizanniv', { body })),
    onSuccess: (status) => {
      qc.setQueryData<FelizAnnivStatus>(FELIZANNIV_KEY, status);
      return qc.invalidateQueries({ queryKey: BIRTHDAYS_KEY });
    },
  });
}

/** `POST /integrations/felizanniv/sync`: queue a sync now. */
export function useSyncFelizAnniv() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async () => unwrap(await api.POST('/api/v1/integrations/felizanniv/sync')),
    onSuccess: (status) => qc.setQueryData<FelizAnnivStatus>(FELIZANNIV_KEY, status),
    onSettled: () => qc.invalidateQueries({ queryKey: FELIZANNIV_KEY }),
  });
}

/** `DELETE /integrations/felizanniv`: forget the connection and the synced birthdays. */
export function useDisconnectFelizAnniv() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async () => {
      unwrap(await api.DELETE('/api/v1/integrations/felizanniv'));
    },
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: FELIZANNIV_KEY }),
        qc.invalidateQueries({ queryKey: BIRTHDAYS_KEY }),
      ]),
  });
}

function birthdaysQuery(from: string, to: string, enabled: boolean) {
  return {
    queryKey: [...BIRTHDAYS_KEY, from, to] as const,
    enabled,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/birthdays', { params: { query: { from, to } } })),
  };
}

/** True when birthdays should be drawn: switched on here and something has been synced. */
export function useBirthdaysVisible(): boolean {
  const [show] = useShowBirthdays();
  const status = useFelizAnnivStatus();
  return show && !!status.data?.configured && status.data.count > 0;
}

/** One birthday as an overlay entry (drawn like a holiday, never a non-working day). */
export function toOverlayDay(b: BirthdayOccurrence): HolidayDay {
  return {
    id: `birthday:${b.id}:${b.date}`,
    date: b.date,
    name: b.name,
    calendarName: 'Birthday',
    colour: 'pink',
    nonWorking: false,
    estimated: false,
    kind: 'birthday',
    age: b.age,
  };
}

export function groupBirthdays(list: readonly BirthdayOccurrence[]): Map<string, HolidayDay[]> {
  const out = new Map<string, HolidayDay[]>();
  for (const b of list) {
    const day = toOverlayDay(b);
    const bucket = out.get(b.date);
    if (bucket) bucket.push(day);
    else out.set(b.date, [day]);
  }
  return out;
}

/** Birthdays of the whole `year` keyed by date (empty while hidden or not connected). */
export function useBirthdayOverlay(year: number): ReadonlyMap<string, HolidayDay[]> {
  const visible = useBirthdaysVisible();
  const birthdays = useQuery(birthdaysQuery(`${year}-01-01`, `${year}-12-31`, visible));
  return useMemo(
    () => (visible && birthdays.data ? groupBirthdays(birthdays.data) : NO_HOLIDAYS),
    [visible, birthdays.data],
  );
}

/**
 * Everything drawn over the calendar days of `year`: holidays of the enabled calendars, then
 * birthdays. Each part follows its own "show" switch.
 */
export function useCalendarOverlay(year: number): ReadonlyMap<string, HolidayDay[]> {
  const holidays = useHolidayOverlay(year);
  const birthdays = useBirthdayOverlay(year);
  return useMemo(() => mergeOverlays(holidays, birthdays), [holidays, birthdays]);
}

export function mergeOverlays(
  first: ReadonlyMap<string, HolidayDay[]>,
  second: ReadonlyMap<string, HolidayDay[]>,
): ReadonlyMap<string, HolidayDay[]> {
  if (second.size === 0) return first;
  if (first.size === 0) return second;
  const out = new Map(first);
  for (const [date, list] of second) out.set(date, [...(out.get(date) ?? []), ...list]);
  return out;
}

/** Stable `combine` for useQueries: the data of each result (structurally shared). */
function dataOf(results: { data?: BirthdayOccurrence[] }[]) {
  return results.map((r) => r.data);
}

/**
 * Birthdays between `from` and `to` (inclusive ISO dates, any length) by date, for the agenda.
 * Fetched per calendar year so the cache is shared with the calendar views.
 */
export function useBirthdaysBetween(from: string, to: string): ReadonlyMap<string, HolidayDay[]> {
  const visible = useBirthdaysVisible();
  const years: number[] = [];
  for (let y = Number(from.slice(0, 4)); y <= Number(to.slice(0, 4)); y += 1) years.push(y);
  const lists = useQueries({
    queries: years.map((y) => birthdaysQuery(`${y}-01-01`, `${y}-12-31`, visible)),
    combine: dataOf,
  });
  return useMemo(() => {
    if (!visible) return NO_HOLIDAYS;
    const all = lists.flatMap((d) => d ?? []).filter((b) => b.date >= from && b.date <= to);
    return groupBirthdays(all);
  }, [visible, from, to, lists]);
}
