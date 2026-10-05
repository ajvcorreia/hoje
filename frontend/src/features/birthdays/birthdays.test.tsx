import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, problem, renderApp } from '../../test/utils';
import { SHOW_BIRTHDAYS_KEY } from '../../lib/showBirthdays';
import { holidayLabel, holidayText, overlayAria, type HolidayDay } from '../holidays/api';
import { keysForChange } from '../realtime/realtimeKeys';
import { groupBirthdays, mergeOverlays, toOverlayDay } from './api';

const NOW = new Date(2026, 9, 2, 12, 0, 0); // Friday 2 October 2026, local time
const minutesAgo = (n: number) => new Date(NOW.getTime() - n * 60_000).toISOString();

const settingsBase = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/me': ME,
  'GET /api/v1/settings/email': { configured: true, from_address: 'hoje@example.com' },
  'GET /api/v1/settings/email/log': [],
};

const NOT_CONNECTED = {
  configured: false,
  base_url: null,
  api_key_hint: null,
  enabled: false,
  last_sync_at: null,
  last_success_at: null,
  last_error: null,
  count: 0,
  sync_pending: false,
};

function connected(overrides: Record<string, unknown> = {}) {
  return {
    configured: true,
    base_url: 'https://fa.example.com',
    api_key_hint: 'fa_live_ab…',
    enabled: true,
    last_sync_at: minutesAgo(5),
    last_success_at: minutesAgo(5),
    last_error: null,
    count: 2,
    sync_pending: false,
    ...overrides,
  };
}

function birthday(id: string, date: string, name: string, age: number | null = null) {
  return {
    id,
    name,
    date,
    birth_month: Number(date.slice(5, 7)),
    birth_day: Number(date.slice(8, 10)),
    birth_year: age === null ? null : Number(date.slice(0, 4)) - age,
    age,
  };
}

async function section() {
  const heading = await screen.findByRole('heading', { name: 'FelizAnniv birthdays' });
  return heading.closest('section')!;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('settings › FelizAnniv birthdays', () => {
  it('connects with an address and key, then never shows the key again', async () => {
    let status: Record<string, unknown> = NOT_CONNECTED;
    const api = mockApi({
      ...settingsBase,
      'GET /api/v1/integrations/felizanniv': () => status,
      'PUT /api/v1/integrations/felizanniv': () => {
        status = connected({
          last_success_at: null,
          last_sync_at: null,
          count: 0,
          sync_pending: true,
        });
        return status;
      },
    });
    renderApp('/settings');
    const box = await section();
    expect(within(box).getByText(/Settings › API Keys › New API Key/)).toBeInTheDocument();
    expect(within(box).queryByRole('button', { name: 'Sync now' })).not.toBeInTheDocument();

    await userEvent.type(
      within(box).getByLabelText('FelizAnniv address'),
      'https://fa.example.com',
    );
    const key = within(box).getByLabelText('API key');
    expect(key).toHaveAttribute('type', 'password');
    await userEvent.type(key, 'fa_live_secretvalue123');
    await userEvent.click(within(box).getByRole('button', { name: 'Save & test' }));

    await waitFor(() =>
      expect(api.callsTo('PUT', '/api/v1/integrations/felizanniv')).toHaveLength(1),
    );
    expect(api.callsTo('PUT', '/api/v1/integrations/felizanniv')[0]?.body).toEqual({
      base_url: 'https://fa.example.com',
      api_key: 'fa_live_secretvalue123',
    });
    expect(await within(box).findByText(/Connected\. The birthdays appear/)).toBeInTheDocument();
    expect(within(box).getByText('fa_live_ab…')).toBeInTheDocument();
    expect(within(box).getByText('Syncing…')).toBeInTheDocument();
    expect(within(box).getByLabelText('API key')).toHaveValue('');
    expect(box).not.toHaveTextContent('fa_live_secretvalue123');
  });

  it('shows the server message when the connection test fails', async () => {
    mockApi({
      ...settingsBase,
      'GET /api/v1/integrations/felizanniv': NOT_CONNECTED,
      'PUT /api/v1/integrations/felizanniv': problem(400, 'FelizAnniv rejected the API key'),
    });
    renderApp('/settings');
    const box = await section();
    await userEvent.type(
      within(box).getByLabelText('FelizAnniv address'),
      'http://192.168.1.5:4000',
    );
    await userEvent.type(within(box).getByLabelText('API key'), 'fa_live_wrongwrong');
    await userEvent.click(within(box).getByRole('button', { name: 'Save & test' }));
    expect(await within(box).findByRole('alert')).toHaveTextContent(
      'FelizAnniv rejected the API key',
    );
  });

  it('shows the status, keeps the key when only the address changes and syncs on demand', async () => {
    const api = mockApi({
      ...settingsBase,
      'GET /api/v1/integrations/felizanniv': connected({
        last_error: 'FelizAnniv did not answer in time',
        last_sync_at: minutesAgo(1),
      }),
      'PUT /api/v1/integrations/felizanniv': connected({ base_url: 'https://fa2.example.com' }),
      'POST /api/v1/integrations/felizanniv/sync': () =>
        new Response(JSON.stringify(connected({ sync_pending: true })), {
          status: 202,
          headers: { 'content-type': 'application/json' },
        }),
    });
    renderApp('/settings');
    const box = await section();
    expect(await within(box).findByText('Last synced 5 minutes ago · 2 birthdays')).toBeVisible();
    expect(
      within(box).getByText(/Last sync failed 1 minute ago: FelizAnniv did not answer/),
    ).toBeVisible();
    const key = within(box).getByLabelText('API key');
    expect(key).toHaveValue('');
    expect(key).not.toBeRequired();
    expect(key).toHaveAttribute('placeholder', 'Leave empty to keep fa_live_ab…');
    const url = within(box).getByLabelText('FelizAnniv address');
    expect(url).toHaveValue('https://fa.example.com');

    await userEvent.clear(url);
    await userEvent.type(url, 'https://fa2.example.com');
    await userEvent.click(within(box).getByRole('button', { name: 'Save & test' }));
    await waitFor(() =>
      expect(api.callsTo('PUT', '/api/v1/integrations/felizanniv')).toHaveLength(1),
    );
    expect(api.callsTo('PUT', '/api/v1/integrations/felizanniv')[0]?.body).toEqual({
      base_url: 'https://fa2.example.com',
    });

    await userEvent.click(within(box).getByRole('button', { name: 'Sync now' }));
    await waitFor(() =>
      expect(api.callsTo('POST', '/api/v1/integrations/felizanniv/sync')).toHaveLength(1),
    );
  });

  it('disconnects after confirming', async () => {
    let status: Record<string, unknown> = connected();
    const api = mockApi({
      ...settingsBase,
      'GET /api/v1/integrations/felizanniv': () => status,
      'DELETE /api/v1/integrations/felizanniv': () => {
        status = NOT_CONNECTED;
        return new Response(null, { status: 204 });
      },
    });
    renderApp('/settings');
    const box = await section();
    await userEvent.click(await within(box).findByRole('button', { name: 'Disconnect' }));
    const dialog = await screen.findByRole('dialog', { name: 'Disconnect FelizAnniv?' });
    expect(dialog).toHaveTextContent('the 2 birthdays synced to Hoje');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Disconnect' }));
    await waitFor(() =>
      expect(api.callsTo('DELETE', '/api/v1/integrations/felizanniv')).toHaveLength(1),
    );
    await waitFor(() =>
      expect(within(box).queryByRole('button', { name: 'Sync now' })).not.toBeInTheDocument(),
    );
  });

  it('has a per-device "Show birthdays" switch', async () => {
    mockApi({ ...settingsBase, 'GET /api/v1/integrations/felizanniv': connected() });
    renderApp('/settings');
    const box = await section();
    const toggle = within(box).getByRole('checkbox', { name: /Show birthdays in the calendar/ });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(window.localStorage.getItem(SHOW_BIRTHDAYS_KEY)).toBe('off');
  });
});

describe('birthday overlay helpers', () => {
  const ana = toOverlayDay(birthday('b1', '2026-10-02', 'Ana', 34));
  const leo = toOverlayDay(birthday('b2', '2026-10-02', 'Leo'));
  const freedom: HolidayDay = {
    id: 'h1',
    date: '2026-10-02',
    name: 'Freedom Day',
    calendarName: 'Portugal',
    colour: 'green',
    nonWorking: true,
    estimated: false,
  };

  it('labels birthdays with a cake and the age', () => {
    expect(ana).toMatchObject({ kind: 'birthday', colour: 'pink', nonWorking: false, age: 34 });
    expect(holidayText([ana, leo])).toBe('\u{1F382} Ana (34) · \u{1F382} Leo');
    expect(holidayLabel(ana)).toBe('Birthday · Ana (34)');
    expect(holidayText([freedom, ana])).toBe('Freedom Day · \u{1F382} Ana (34)');
  });

  it('keeps holiday-only accessible names unchanged and adds birthdays', () => {
    expect(overlayAria([freedom])).toBe('holiday: Freedom Day');
    expect(overlayAria([freedom, ana, leo])).toBe('holiday: Freedom Day, birthday: Ana (34) · Leo');
    expect(overlayAria([ana, leo], ', ')).toBe('birthday: Ana (34), Leo');
  });

  it('merges birthdays after the holidays of the same day', () => {
    const holidays = new Map([['2026-10-02', [freedom]]]);
    const merged = mergeOverlays(
      holidays,
      groupBirthdays([birthday('b1', '2026-10-02', 'Ana', 34)]),
    );
    expect(merged.get('2026-10-02')?.map((d) => d.name)).toEqual(['Freedom Day', 'Ana']);
    expect(holidays.get('2026-10-02')).toHaveLength(1); // inputs are not mutated
  });

  it('refreshes birthdays and the status on a realtime birthday change', () => {
    expect(
      keysForChange({ entity: 'birthday', op: 'update', id: 'x', version: 0, client_id: null }),
    ).toEqual([['birthdays'], ['integrations', 'felizanniv']]);
  });
});

describe('mobile day view: birthday cards', () => {
  beforeEach(() => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
  });

  it('shows the birthdays of the selected day as read-only cards and a Birthdays chip', async () => {
    const api = mockApi({
      'GET /api/v1/auth/state': authState(),
      'GET /api/v1/categories': [],
      'GET /api/v1/events': { occurrences: [] },
      'GET /api/v1/holiday-calendars': [],
      'GET /api/v1/integrations/felizanniv': connected(),
      'GET /api/v1/birthdays': [birthday('b1', '2026-10-02', 'Ana', 34)],
    });
    renderApp();
    const list = await screen.findByRole('list', { name: 'Birthdays' });
    expect(within(list).getByText('Ana')).toBeInTheDocument();
    expect(within(list).getByText('Birthday · turns 34')).toBeInTheDocument();
    expect(within(list).queryByRole('button')).not.toBeInTheDocument();
    expect(api.callsTo('GET', '/api/v1/birthdays')[0]?.search).toBe(
      '?from=2026-01-01&to=2026-12-31',
    );

    const chip = screen.getByRole('button', { name: 'Birthdays' });
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(chip);
    await waitFor(() =>
      expect(screen.queryByRole('list', { name: 'Birthdays' })).not.toBeInTheDocument(),
    );
  });

  it('asks for no birthdays when FelizAnniv is not connected', async () => {
    const api = mockApi({
      'GET /api/v1/auth/state': authState(),
      'GET /api/v1/categories': [],
      'GET /api/v1/events': { occurrences: [] },
      'GET /api/v1/holiday-calendars': [],
      'GET /api/v1/integrations/felizanniv': NOT_CONNECTED,
    });
    renderApp();
    await waitFor(() =>
      expect(api.callsTo('GET', '/api/v1/integrations/felizanniv').length).toBeGreaterThan(0),
    );
    await screen.findByText('No events');
    expect(api.callsTo('GET', '/api/v1/birthdays')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: 'Birthdays' })).not.toBeInTheDocument();
  });
});

describe('desktop month grid: birthday overlay', () => {
  it('draws "🎂 Name (age)" on an empty day, never shades it and lists it in the popover', async () => {
    mockApi({
      'GET /api/v1/auth/state': authState(),
      'GET /api/v1/categories': [],
      'GET /api/v1/events': { occurrences: [] },
      'GET /api/v1/holiday-calendars': [],
      'GET /api/v1/integrations/felizanniv': connected(),
      'GET /api/v1/birthdays': [
        birthday('b1', '2026-03-10', 'Ana', 34),
        birthday('b2', '2026-02-28', 'Leap'),
      ],
    });
    renderApp();
    // The full 12-month grid (with text measuring) is slow to mount under a loaded test run.
    await waitFor(() => expect(document.querySelector('.cal-hol')).not.toBeNull(), {
      timeout: 5000,
    });
    const cell = document.querySelector<HTMLElement>('[data-date="2026-03-10"]')!;
    const mark = cell.querySelector('.cal-hol')!;
    expect(mark).toHaveTextContent('\u{1F382} Ana (34)');
    expect(mark).toHaveAttribute('data-birthday', 'true');
    expect(mark).toHaveAttribute('data-cat', 'pink');
    expect(cell).not.toHaveAttribute('data-holiday-off');
    expect(cell).toHaveAccessibleName(/birthday: Ana \(34\)/);

    await userEvent.click(cell);
    const popover = await screen.findByRole('dialog', { hidden: true, name: /Events on/ });
    const list = within(popover).getByRole('list', { hidden: true, name: 'Birthdays' });
    expect(list).toHaveTextContent('Ana (34)');
  });
});
