import { QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { vi } from 'vitest';
import { csrfStore } from '../api/csrf';
import { createQueryClient } from '../app/queryClient';
import { routes } from '../app/router';

export interface RecordedCall {
  method: string;
  path: string;
  body: unknown;
}

type Reply =
  Response | object | ((call: RecordedCall) => Response | object | Promise<Response | object>);

export function problem(status: number, detail?: string, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify({ title: `Error ${status}`, status, detail }), {
    status,
    headers: { 'content-type': 'application/problem+json', ...headers },
  });
}

/**
 * Stubs global fetch. Keys look like "POST /api/v1/auth/login". Plain objects reply 200 JSON;
 * `null` replies 204. Unmatched requests get a 404 problem.
 */
export function mockApi(routesTable: Record<string, Reply | null>) {
  const calls: RecordedCall[] = [];
  const fetchMock = vi.fn(async (input: Request) => {
    const url = new URL(input.url);
    let body: unknown = undefined;
    try {
      const text = await input.clone().text();
      body = text ? JSON.parse(text) : undefined;
    } catch {
      body = undefined;
    }
    const call = { method: input.method, path: url.pathname, body };
    calls.push(call);
    const key = `${input.method} ${url.pathname}`;
    if (!(key in routesTable)) return problem(404, `no mock for ${key}`);
    const reply = routesTable[key];
    if (reply === null) return new Response(null, { status: 204 });
    const resolved = typeof reply === 'function' ? await reply(call) : reply;
    return resolved instanceof Response ? resolved : Response.json(resolved);
  });
  vi.stubGlobal('fetch', fetchMock);
  return {
    calls,
    callsTo: (method: string, path: string) =>
      calls.filter((c) => c.method === method && c.path === path),
  };
}

export const ME = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'ana@example.com',
  created_at: '2026-01-01T00:00:00Z',
  timezone: 'Europe/Lisbon',
  totp_enabled: false,
  weekend_days: [6, 7],
};

export function authState(overrides: Record<string, unknown> = {}) {
  return {
    registration_open: false,
    authenticated: true,
    stage: 'active',
    csrf_token: 'csrf-1',
    user: ME,
    ...overrides,
  };
}

export const LOGGED_OUT = {
  registration_open: false,
  authenticated: false,
  stage: null,
  csrf_token: 'csrf-anon',
  user: null,
};

export function renderApp(path = '/') {
  csrfStore.set(null);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, queryClient };
}
