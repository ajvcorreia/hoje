import createClient, { type Middleware } from 'openapi-fetch';
import { getClientId } from './clientId';
import { csrfStore } from './csrf';
import type { paths } from './schema';

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export interface ProblemFieldError {
  loc?: unknown;
  msg?: string;
  [key: string]: unknown;
}

/** An RFC 9457 `application/problem+json` response (or a synthetic one for other failures). */
export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string | null;
  readonly type: string;
  readonly errors: ProblemFieldError[];
  /** The full parsed problem body, e.g. the `current` item of a 409 conflict. */
  readonly body: Record<string, unknown>;
  /** Seconds from a `Retry-After` header (429 lockouts), when present. */
  readonly retryAfter: number | null;

  constructor(
    status: number,
    body: Record<string, unknown> = {},
    retryAfter: number | null = null,
  ) {
    const title = typeof body.title === 'string' ? body.title : `Request failed (${status})`;
    const detail = typeof body.detail === 'string' ? body.detail : null;
    super(detail ?? title);
    this.name = 'ApiError';
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.type = typeof body.type === 'string' ? body.type : 'about:blank';
    this.errors = Array.isArray(body.errors) ? (body.errors as ProblemFieldError[]) : [];
    this.body = body;
    this.retryAfter = retryAfter;
  }
}

function parseRetryAfter(value: string | null): number | null {
  if (!value) return null;
  const seconds = Number(value);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    const token = csrfStore.get();
    if (token && !SAFE_METHODS.has(request.method.toUpperCase())) {
      request.headers.set('X-CSRF-Token', token);
    }
    return request;
  },
};

/** Tags every write with this tab's id so the live-sync stream can tell own changes from others. */
export const clientIdMiddleware: Middleware = {
  onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method.toUpperCase())) {
      request.headers.set('X-Hoje-Client', getClientId());
    }
    return request;
  },
};

export const problemMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return undefined;
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('application/problem+json')) return undefined;
    let body: Record<string, unknown> = {};
    try {
      const parsed: unknown = await response.clone().json();
      if (parsed && typeof parsed === 'object') body = parsed as Record<string, unknown>;
    } catch {
      // Malformed problem body: fall back to the status alone.
    }
    throw new ApiError(response.status, body, parseRetryAfter(response.headers.get('retry-after')));
  },
};

export interface ApiClientOptions {
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
}

export function createApiClient(options: ApiClientOptions = {}) {
  const client = createClient<paths>({
    // Absolute same-origin URL: Request() rejects relative URLs outside a browser (tests).
    baseUrl: options.baseUrl ?? globalThis.location?.origin ?? '',
    credentials: 'same-origin',
    fetch: options.fetch ?? ((request: Request) => globalThis.fetch(request)),
  });
  client.use(csrfMiddleware, clientIdMiddleware, problemMiddleware);
  return client;
}

export const api = createApiClient();

/**
 * Unwraps an openapi-fetch result for use in TanStack Query functions:
 * returns `data`, or throws an ApiError for any non-2xx (problem+json ones already throw in middleware).
 */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    const body =
      result.error && typeof result.error === 'object'
        ? (result.error as Record<string, unknown>)
        : {};
    if (result.response.ok && result.data === undefined) {
      // 204 and friends carry no body; callers of such endpoints should not use unwrap.
      return undefined as T;
    }
    throw new ApiError(
      result.response.status,
      body,
      parseRetryAfter(result.response.headers.get('retry-after')),
    );
  }
  return result.data;
}
