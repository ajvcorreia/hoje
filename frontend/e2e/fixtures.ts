import { randomBytes, randomUUID } from 'node:crypto';
import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';

export { expect };

export interface Account {
  email: string;
  password: string;
}

export interface Category {
  id: string;
  name: string;
}

export interface ApiEvent {
  id: string;
  title: string;
  category_id: string;
  start_date: string;
}

/** Thin authenticated client for arranging test data quickly (UI is used for what is under test). */
export class Api {
  constructor(
    private readonly request: APIRequestContext,
    private readonly origin: string,
    private readonly csrf: string,
  ) {}

  private headers() {
    return { Origin: this.origin, 'X-CSRF-Token': this.csrf };
  }

  async categories(): Promise<Category[]> {
    const res = await this.request.get('/api/v1/categories');
    expect(res.ok()).toBeTruthy();
    return (await res.json()) as Category[];
  }

  async createEvent(title: string, date: string, extra: Record<string, unknown> = {}) {
    const res = await this.request.post('/api/v1/events', {
      headers: this.headers(),
      data: { title, start_date: date, end_date: date, all_day: true, ...extra },
    });
    expect(res.status(), await res.text()).toBe(201);
    return ((await res.json()) as { event: ApiEvent }).event;
  }

  /** Per-user settings (PATCH /me), e.g. `{ max_events_per_day: 4 }`. */
  async patchMe(data: Record<string, unknown>) {
    const res = await this.request.patch('/api/v1/me', { headers: this.headers(), data });
    expect(res.ok(), await res.text()).toBeTruthy();
  }

  /** POST that returns the raw response, for tests that look at status codes. */
  async post(path: string, data: unknown, headers: Record<string, string> = {}) {
    return this.request.post(path, { headers: { ...this.headers(), ...headers }, data });
  }

  async events(from: string, to: string): Promise<ApiEvent[]> {
    const res = await this.request.get('/api/v1/events', { params: { from, to } });
    expect(res.ok()).toBeTruthy();
    const body = (await res.json()) as { occurrences: { event: ApiEvent }[] };
    return body.occurrences.map((o) => o.event);
  }
}

/** Registers a fresh user through the API; the session cookie lands in the page's context. */
export async function registerUser(page: Page, baseURL: string): Promise<Account> {
  const origin = new URL(baseURL).origin;
  const account: Account = {
    email: `e2e-${randomUUID()}@example.com`,
    password: randomBytes(12).toString('base64url'),
  };
  const request = page.context().request;
  const res = await request.post('/api/v1/auth/register', {
    headers: { Origin: origin },
    data: account,
  });
  expect(res.status(), await res.text()).toBe(201);
  return account;
}

interface Fixtures {
  /** A freshly registered, logged-in user; `page` is already authenticated as them. */
  account: Account;
  api: Api;
}

export const test = base.extend<Fixtures>({
  account: async ({ page, baseURL }, use) => {
    await use(await registerUser(page, baseURL ?? ''));
  },
  api: async ({ page, baseURL, account }, use) => {
    // `account` ran first, so the context already holds the session: just fetch the CSRF token.
    void account;
    const request = page.context().request;
    const state = await request.get('/api/v1/auth/state');
    const { csrf_token: csrf } = (await state.json()) as { csrf_token: string };
    await use(new Api(request, new URL(baseURL ?? '').origin, csrf));
  },
});

/** `YYYY-MM-DD` for `day` of the current month. */
export function dateInCurrentMonth(day: number): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(day)}`;
}

/** Today as YYYY-MM-DD in the runner time zone (same as the browser in the container). */
export function todayIso(): string {
  return dateInCurrentMonth(new Date().getDate());
}
