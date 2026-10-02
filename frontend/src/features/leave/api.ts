import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../../api/client';
import type { LeaveImpact } from '../../api/types';
import { useCategories } from '../categories/api';

/** Root of every leave query: balances (`['leave', 'balance', year]`) and previews. */
export const LEAVE_KEY = ['leave'] as const;
export const balanceKey = (year: number) => [...LEAVE_KEY, 'balance', year] as const;

/** Vacation balance of one calendar year (`GET /leave/balance`). */
export function useLeaveBalance(year: number, enabled = true) {
  return useQuery({
    queryKey: balanceKey(year),
    enabled,
    queryFn: async () => unwrap(await api.GET('/api/v1/leave/balance', { params: { query: { year } } })),
  });
}

export interface PolicyValues {
  allowance_days: number;
  carried_over_days: number;
}

/** `PUT /leave/policies/{year}`. Refreshes every leave query afterwards. */
export function useSavePolicy() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async ({ year, values }: { year: number; values: PolicyValues }) =>
      unwrap(
        await api.PUT('/api/v1/leave/policies/{year}', {
          params: { path: { year } },
          body: values,
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: LEAVE_KEY }),
  });
}

/** True when the user has at least one category that counts as vacation. */
export function useHasVacationCategory(): boolean {
  const { data } = useCategories();
  return data?.some((c) => c.is_leave) ?? false;
}

export interface PreviewParams {
  startDate: string;
  endDate: string;
  categoryId: string;
  repeat: 'none' | 'monthly' | 'yearly';
  repeatUntil: string;
  excludeEventId?: string;
}

/** `POST /leave/preview`: what saving this booking would do to the balance ([] if not vacation). */
export function useLeavePreview(params: PreviewParams | null) {
  return useQuery({
    queryKey: [...LEAVE_KEY, 'preview', params] as const,
    enabled: params !== null,
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<LeaveImpact[]> => {
      if (!params) return [];
      return unwrap(
        await api.POST('/api/v1/leave/preview', {
          body: {
            start_date: params.startDate,
            end_date: params.endDate,
            category_id: params.categoryId,
            repeat: params.repeat,
            repeat_until: params.repeat !== 'none' && params.repeatUntil ? params.repeatUntil : null,
            exclude_event_id: params.excludeEventId ?? null,
          },
        }),
      );
    },
  });
}

/** 17 -> "17", 16.5 -> "16.5", 16.25 -> "16.25" (never a trailing ".0"). */
export function formatDays(value: number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '0';
  const rounded = Math.round(n * 100) / 100;
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

/** "1 day" / "2 days" / "0.5 days". */
export function daysLabel(value: number, unit = 'day'): string {
  return `${formatDays(value)} ${unit}${Number(value) === 1 ? '' : 's'}`;
}

/** Header pill text: "Vacation: 17 left" or, when overdrawn, "Vacation: 2 over". */
export function pillText(remaining: number): string {
  const n = Number(remaining);
  return n < 0 ? `Vacation: ${formatDays(-n)} over` : `Vacation: ${formatDays(n)} left`;
}
