import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/client';

const AUTH_STATE_KEY = ['auth', 'state'] as const;

export function createQueryClient(): QueryClient {
  // A 401 from any protected request means the session is gone: refresh the auth state
  // so the route guard sends the user to the login page.
  const onUnauthorized = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) {
      void client.invalidateQueries({ queryKey: AUTH_STATE_KEY });
    }
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.queryKey[0] !== 'auth') onUnauthorized(error);
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => {
        if (mutation.meta?.protected) onUnauthorized(error);
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // API problems (4xx/5xx with a body) are deterministic; only retry network hiccups.
        retry: (failureCount, error) => !(error instanceof ApiError) && failureCount < 2,
      },
    },
  });
  return client;
}
