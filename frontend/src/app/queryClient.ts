import { QueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/client';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // API problems (4xx/5xx with a body) are deterministic; only retry network hiccups.
        retry: (failureCount, error) => !(error instanceof ApiError) && failureCount < 2,
      },
    },
  });
}
