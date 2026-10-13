import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '../../api/client';
import type { FelizAnnivStatus } from '../../api/types';

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
    onSuccess: (status) => qc.setQueryData<FelizAnnivStatus>(FELIZANNIV_KEY, status),
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

/** `DELETE /integrations/felizanniv`: stop syncing; the birthday events stay in the calendar. */
export function useDisconnectFelizAnniv() {
  const qc = useQueryClient();
  return useMutation({
    meta: { protected: true },
    mutationFn: async () => {
      unwrap(await api.DELETE('/api/v1/integrations/felizanniv'));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: FELIZANNIV_KEY }),
  });
}
