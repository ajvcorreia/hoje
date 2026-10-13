import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, problem, renderApp } from '../../test/utils';
import { overlayAria, holidayText, type HolidayDay } from '../holidays/api';
import { keysForChange } from '../realtime/realtimeKeys';

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

  it('explains that the sync goes both ways and that birthdays are ordinary events', async () => {
    mockApi({ ...settingsBase, 'GET /api/v1/integrations/felizanniv': NOT_CONNECTED });
    renderApp('/settings');
    const box = await section();
    expect(box).toHaveTextContent(/edit or delete/);
    expect(box).toHaveTextContent(/changes go both ways/);
    expect(box).toHaveTextContent(/Hoje wins/);
    expect(box).not.toHaveTextContent(/never changes anything in FelizAnniv/);
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

  it('disconnects after confirming, and says the birthdays stay as events', async () => {
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
    expect(dialog).toHaveTextContent('The 2 birthdays stay in your calendar as ordinary events');
    expect(dialog).toHaveTextContent('Nothing changes in FelizAnniv');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Disconnect' }));
    await waitFor(() =>
      expect(api.callsTo('DELETE', '/api/v1/integrations/felizanniv')).toHaveLength(1),
    );
    await waitFor(() =>
      expect(within(box).queryByRole('button', { name: 'Sync now' })).not.toBeInTheDocument(),
    );
  });

  it('no longer has a per-device "Show birthdays" switch (they are ordinary events)', async () => {
    mockApi({ ...settingsBase, 'GET /api/v1/integrations/felizanniv': connected() });
    renderApp('/settings');
    const box = await section();
    expect(within(box).queryByRole('checkbox')).not.toBeInTheDocument();
  });
});

describe('overlay helpers (holidays only)', () => {
  const freedom: HolidayDay = {
    id: 'h1',
    date: '2026-10-02',
    name: 'Freedom Day',
    calendarName: 'Portugal',
    colour: 'green',
    nonWorking: true,
    estimated: false,
  };

  it('draws and announces the holiday name', () => {
    expect(holidayText([freedom])).toBe('Freedom Day');
    expect(overlayAria([freedom])).toBe('holiday: Freedom Day');
    expect(overlayAria([])).toBe('');
  });
});

describe('realtime', () => {
  it('refreshes only the connection status on a birthday change (events arrive as events)', () => {
    expect(
      keysForChange({ entity: 'birthday', op: 'update', id: 'x', version: 0, client_id: null }),
    ).toEqual([['integrations', 'felizanniv']]);
  });
});

describe('calendar: birthdays are ordinary events', () => {
  beforeEach(() => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
  });

  it('shows a synced birthday as an event card and asks for no birthday overlay', async () => {
    const category = {
      id: 'cat-birthdays',
      name: 'Birthdays',
      colour: 'pink',
      icon: null,
      sort_order: 0,
      is_leave: false,
      hidden: false,
      version: 1,
    };
    const event = {
      id: 'ev-ana',
      category_id: category.id,
      title: "Ana's birthday",
      notes: null,
      start_date: '1992-10-02',
      end_date: '1992-10-02',
      all_day: true,
      start_time: null,
      end_time: null,
      timezone: 'Europe/Lisbon',
      repeat: 'yearly',
      repeat_until: null,
      counts_as_leave: false,
      label_vertical: false,
      day_order: 0,
      reminders: [],
      felizanniv: true,
      version: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    const api = mockApi({
      'GET /api/v1/auth/state': authState(),
      'GET /api/v1/categories': [category],
      'GET /api/v1/events': {
        occurrences: [
          {
            event_id: event.id,
            occurrence_start: '2026-10-02',
            occurrence_end: '2026-10-02',
            event,
          },
        ],
      },
      'GET /api/v1/holiday-calendars': [],
      'GET /api/v1/integrations/felizanniv': connected(),
    });
    renderApp();
    expect(await screen.findByText("Ana's birthday")).toBeInTheDocument();
    expect(api.callsTo('GET', '/api/v1/birthdays')).toHaveLength(0);
    // The Birthdays category has the same chip as any category, and there is no extra one.
    expect(screen.getAllByRole('button', { name: /^Birthdays/ })).toHaveLength(1);
  });
});
