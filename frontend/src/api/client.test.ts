import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from './client';
import { csrfStore } from './csrf';

function setup(respond: () => Response = () => Response.json({})) {
  const fetchMock = vi.fn<(req: Request) => Promise<Response>>(async () => respond());
  const client = createApiClient({
    baseUrl: 'http://localhost',
    fetch: fetchMock as unknown as typeof fetch,
  });
  const lastRequest = (): Request => {
    const call = fetchMock.mock.calls.at(-1);
    if (!call) throw new Error('fetch not called');
    return call[0];
  };
  return { client, lastRequest };
}

afterEach(() => csrfStore.set(null));

describe('CSRF middleware', () => {
  it('does not add the header to GET requests', async () => {
    csrfStore.set('tok');
    const { client, lastRequest } = setup();
    await client.GET('/api/v1/auth/state');
    expect(lastRequest().headers.get('X-CSRF-Token')).toBeNull();
  });

  it('adds the header to unsafe methods', async () => {
    csrfStore.set('tok-123');
    const { client, lastRequest } = setup();
    await client.POST('/api/v1/auth/logout');
    expect(lastRequest().headers.get('X-CSRF-Token')).toBe('tok-123');
    await client.DELETE('/api/v1/events/{event_id}', {
      params: { path: { event_id: '00000000-0000-0000-0000-000000000000' } },
    });
    expect(lastRequest().headers.get('X-CSRF-Token')).toBe('tok-123');
  });

  it('omits the header when no token is known', async () => {
    const { client, lastRequest } = setup();
    await client.POST('/api/v1/auth/logout');
    expect(lastRequest().headers.get('X-CSRF-Token')).toBeNull();
  });
});

describe('problem+json middleware', () => {
  it('turns problem responses into ApiError', async () => {
    const { client } = setup(
      () =>
        new Response(
          JSON.stringify({ type: 'about:blank', title: 'Conflict', status: 409, detail: 'Stale' }),
          {
            status: 409,
            headers: { 'content-type': 'application/problem+json' },
          },
        ),
    );
    const err = await client.GET('/api/v1/me').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, title: 'Conflict', detail: 'Stale' });
  });
});
