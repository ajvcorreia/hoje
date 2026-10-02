import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { createRealtimeController } from './connection';

/** Keeps the live-sync stream open while mounted (the app shell, i.e. authenticated). */
export function useRealtime() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const controller = createRealtimeController({ queryClient });
    controller.start();
    return () => controller.stop();
  }, [queryClient]);
}
