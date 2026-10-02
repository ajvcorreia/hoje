import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { api, unwrap } from '../../api/client';
import type { Category, Holiday, HolidayCalendar } from '../../api/types';
import { useShowHolidays } from '../../lib/showHolidays';
import { LEAVE_KEY } from '../leave/api';

/** Root of every holidays query: `['holidays', from, to]`. */
export const HOLIDAYS_KEY = ['holidays'] as const;
export const CALENDARS_KEY = ['holiday-calendars'] as const;

type Colour = Category['colour'];

/** Holidays of the ENABLED calendars overlapping `[from, to]` (inclusive ISO dates). */
export function useHolidays(from: string, to: string, enabled = true) {
  return useQuery({
    queryKey: [...HOLIDAYS_KEY, from, to] as const,
    enabled,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/holidays', { params: { query: { from, to } } })),
  });
}

/** The user's holiday calendars (PT, AE) with their enabled flag and colour. */
export function useHolidayCalendars() {
  return useQuery({
    queryKey: CALENDARS_KEY,
    queryFn: async () => unwrap(await api.GET('/api/v1/holiday-calendars')),
  });
}

/** Everything that depends on holidays: lists, calendars and the working-day balance. */
function refreshHolidays(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: HOLIDAYS_KEY }),
    qc.invalidateQueries({ queryKey: CALENDARS_KEY }),
    qc.invalidateQueries({ queryKey: LEAVE_KEY }),
  ]);
}

/** `PATCH /holiday-calendars/{id}` (enable / disable, colour). */
export function useUpdateCalendar() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async ({
      id,
      patch,
    }: {
      id: string;
      patch: { enabled?: boolean; colour?: Colour };
    }) =>
      unwrap(
        await api.PATCH('/api/v1/holiday-calendars/{calendar_id}', {
          params: { path: { calendar_id: id } },
          body: patch,
        }),
      ),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: CALENDARS_KEY });
      const previous = qc.getQueryData<HolidayCalendar[]>(CALENDARS_KEY);
      qc.setQueryData<HolidayCalendar[]>(CALENDARS_KEY, (list) =>
        list?.map((c) => (c.id === id ? ({ ...c, ...patch } as HolidayCalendar) : c)),
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) qc.setQueryData(CALENDARS_KEY, context.previous);
    },
    onSettled: () => refreshHolidays(qc),
  });
}

/** `POST /holiday-calendars/{id}/reset`: back to the bundled holidays. */
export function useResetCalendar() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST('/api/v1/holiday-calendars/{calendar_id}/reset', {
          params: { path: { calendar_id: id } },
        }),
      ),
    onSettled: () => refreshHolidays(qc),
  });
}

/** `POST /holiday-calendars/{id}/holidays`. */
export function useCreateHoliday() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async ({
      calendarId,
      body,
    }: {
      calendarId: string;
      body: { date: string; name: string; is_non_working: boolean };
    }) =>
      unwrap(
        await api.POST('/api/v1/holiday-calendars/{calendar_id}/holidays', {
          params: { path: { calendar_id: calendarId } },
          body,
        }),
      ),
    onSettled: () => refreshHolidays(qc),
  });
}

/** `PATCH /holidays/{id}` (name, date, non-working). */
export function useUpdateHoliday() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async ({
      id,
      patch,
    }: {
      id: string;
      patch: { name?: string; date?: string; is_non_working?: boolean };
    }) =>
      unwrap(
        await api.PATCH('/api/v1/holidays/{holiday_id}', {
          params: { path: { holiday_id: id } },
          body: patch,
        }),
      ),
    onSettled: () => refreshHolidays(qc),
  });
}

/** `DELETE /holidays/{id}`. */
export function useDeleteHoliday() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async (id: string) => {
      unwrap(
        await api.DELETE('/api/v1/holidays/{holiday_id}', {
          params: { path: { holiday_id: id } },
        }),
      );
    },
    onSettled: () => refreshHolidays(qc),
  });
}

/** One holiday ready to draw: the calendar's colour and name are resolved. */
export interface HolidayDay {
  id: string;
  date: string;
  name: string;
  /** Calendar name, e.g. "Portugal". */
  calendarName: string;
  /** Palette key. */
  colour: Colour;
  nonWorking: boolean;
  estimated: boolean;
}

const DEFAULT_COLOUR: Record<string, Colour> = { PT: 'green', AE: 'red' };

/** The calendar's colour, or the per-country default when it has none. */
export function calendarColour(calendar: Pick<HolidayCalendar, 'code' | 'colour'>): Colour {
  return (calendar.colour as Colour | undefined) ?? DEFAULT_COLOUR[calendar.code] ?? 'slate';
}

/** "Portugal · Freedom Day" (+ " (estimated)"). */
export function holidayLabel(h: HolidayDay): string {
  return `${h.calendarName} · ${h.name}${h.estimated ? ' (estimated)' : ''}`;
}

export const NO_HOLIDAYS: ReadonlyMap<string, HolidayDay[]> = new Map();

/**
 * Holidays of the whole `year` keyed by date, ready for the calendar views. Empty while the
 * "Holidays" chip is off or nothing is enabled. Query key: `['holidays', from, to]`.
 */
export function useHolidayOverlay(year: number): ReadonlyMap<string, HolidayDay[]> {
  const [show] = useShowHolidays();
  const holidays = useHolidays(`${year}-01-01`, `${year}-12-31`, show);
  const calendars = useHolidayCalendars();
  return useMemo(() => {
    if (!show || !holidays.data || !calendars.data) return NO_HOLIDAYS;
    return groupHolidays(holidays.data, calendars.data);
  }, [show, holidays.data, calendars.data]);
}

export function groupHolidays(
  holidays: readonly Holiday[],
  calendars: readonly HolidayCalendar[],
): Map<string, HolidayDay[]> {
  const byId = new Map(calendars.map((c, index) => [c.id, { calendar: c, index }]));
  const out = new Map<string, HolidayDay[]>();
  const order = new Map<string, number>();
  for (const h of holidays) {
    const entry = byId.get(h.calendar_id);
    if (!entry || !entry.calendar.enabled) continue;
    const day: HolidayDay = {
      id: h.id,
      date: h.date,
      name: h.name,
      calendarName: entry.calendar.name,
      colour: calendarColour(entry.calendar),
      nonWorking: h.is_non_working,
      estimated: h.estimated,
    };
    order.set(h.id, entry.index);
    const bucket = out.get(h.date);
    if (bucket) bucket.push(day);
    else out.set(h.date, [day]);
  }
  for (const bucket of out.values()) {
    bucket.sort(
      (a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0) || a.name.localeCompare(b.name),
    );
  }
  return out;
}

/** True when any holiday of that day is non-working. */
export function isNonWorkingDay(list: readonly HolidayDay[] | undefined): boolean {
  return list?.some((h) => h.nonWorking) ?? false;
}

/** Text drawn in a day cell for its holidays ("Freedom Day"; several are joined with " · "). */
export function holidayText(list: readonly HolidayDay[]): string {
  return list.map((h) => h.name).join(' · ');
}
