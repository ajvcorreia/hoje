import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, renderApp } from '../../test/utils';
import { formatDays, pillText } from './api';

const WORK = 'aaaaaaaa-0000-0000-0000-000000000001';
const VAC = 'aaaaaaaa-0000-0000-0000-000000000003';

const category = (id: string, name: string, isLeave: boolean, sort: number) => ({
  id,
  name,
  colour: isLeave ? 'orange' : 'teal',
  icon: null,
  sort_order: sort,
  is_leave: isLeave,
  hidden: false,
  version: 1,
});

const BALANCE = {
  year: 2026,
  allowance_days: 22,
  carried_over_days: 2,
  used: 4.5,
  planned: 3,
  remaining: 16.5,
  bookings: [
    {
      event_id: 'bbbbbbbb-0000-0000-0000-000000000001',
      title: 'Algarve',
      start_date: '2026-08-03',
      end_date: '2026-08-05',
      days: 3,
    },
  ],
};

function routes(extra: Parameters<typeof mockApi>[0] = {}, withVacation = true) {
  return {
    'GET /api/v1/auth/state': authState({ user: { ...ME, last_category_id: WORK } }),
    'GET /api/v1/categories': [
      category(WORK, 'Work', false, 0),
      ...(withVacation ? [category(VAC, 'Vacation', true, 1)] : []),
    ],
    'GET /api/v1/events': { occurrences: [] },
    'GET /api/v1/leave/balance': BALANCE,
    ...extra,
  } as Parameters<typeof mockApi>[0];
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: new Date(2026, 5, 15, 12) });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('pill text', () => {
  it('formats whole, half and negative balances', () => {
    expect(formatDays(17)).toBe('17');
    expect(pillText(17)).toBe('Vacation: 17 left');
    expect(pillText(16.5)).toBe('Vacation: 16.5 left');
    expect(pillText(-2)).toBe('Vacation: 2 over');
    expect(pillText(0)).toBe('Vacation: 0 left');
  });
});

describe('vacation pill', () => {
  it('shows the remaining days in the header', async () => {
    mockApi(routes());
    renderApp('/settings'); // the header is all we need; the grid makes role queries slow
    expect(
      await screen.findByRole('button', { name: 'Vacation: 16.5 left' }, { timeout: 5000 }),
    ).toBeInTheDocument();
  });

  it('shows overdrawn balances as "over" in the danger colour', async () => {
    mockApi(routes({ 'GET /api/v1/leave/balance': { ...BALANCE, remaining: -3 } }));
    renderApp('/settings');
    const pill = await screen.findByRole('button', { name: 'Vacation: 3 over' }, { timeout: 5000 });
    expect(pill).toHaveClass('text-danger');
  });

  it('is hidden without a vacation category', async () => {
    mockApi(routes({}, false));
    renderApp();
    await screen.findByRole('banner');
    await waitFor(() => expect(document.querySelector('[data-month="0"]')).not.toBeNull());
    expect(screen.queryByRole('button', { name: /^Vacation/ })).not.toBeInTheDocument();
  });

  it('opens a panel with the balance rows and bookings', async () => {
    mockApi(routes());
    renderApp();
    await userEvent.click(
      await screen.findByRole('button', { name: /Vacation: 16.5 left/ }, { timeout: 5000 }),
    );
    const panel = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });
    for (const [label, value] of [
      ['Allowance', '22'],
      ['Carried over', '2'],
      ['Used', '4.5'],
      ['Planned', '3'],
      ['Remaining', '16.5'],
    ] as const) {
      const term = within(panel).getByText(label);
      expect(term.nextElementSibling).toHaveTextContent(value);
    }
    expect(within(panel).getByRole('button', { name: /Algarve/ })).toHaveTextContent('3 days');
    expect(within(panel).getByRole('link', { name: 'Edit allowance' })).toHaveAttribute(
      'href',
      '/settings#vacation',
    );
  });
});

describe('editor preview', () => {
  async function openEditor() {
    await waitFor(() => expect(document.querySelector('[data-date="2026-06-16"]')).not.toBeNull());
    await userEvent.click(document.querySelector<HTMLElement>('[data-date="2026-06-16"]')!);
    await userEvent.click(
      await screen.findByRole('button', { hidden: true, name: 'Add with details' }),
    );
    return screen.findByRole('dialog', { hidden: true, name: 'New event' });
  }

  it('previews a vacation booking once (debounced) and warns when it exceeds', async () => {
    const api = mockApi(
      routes({
        'POST /api/v1/leave/preview': [
          { year: 2026, days: 5, remaining_before: 2, remaining_after: -3, exceeds: true },
        ],
      }),
    );
    renderApp();
    const dialog = await openEditor();
    const select = within(dialog).getByLabelText('Category');
    expect(api.callsTo('POST', '/api/v1/leave/preview')).toHaveLength(0);
    await userEvent.selectOptions(select, 'Vacation');
    await userEvent.selectOptions(select, 'Work');
    await userEvent.selectOptions(select, 'Vacation');
    expect(await within(dialog).findByText(/Uses 5 working days/)).toHaveTextContent(
      '0 left in 2026',
    );
    expect(within(dialog).getByText(/over your remaining balance/)).toHaveTextContent(
      'This is 3 days over your remaining balance',
    );
    expect(api.callsTo('POST', '/api/v1/leave/preview')).toHaveLength(1);
    expect(api.callsTo('POST', '/api/v1/leave/preview')[0]?.body).toMatchObject({
      start_date: '2026-06-16',
      end_date: '2026-06-16',
      category_id: VAC,
    });
  });

  it('shows a toast after saving a booking that exceeds the balance', async () => {
    mockApi(
      routes({
        'POST /api/v1/leave/preview': [],
        'POST /api/v1/events': {
          event: {
            id: 'new-1',
            category_id: VAC,
            title: 'Trip',
            notes: null,
            start_date: '2026-06-16',
            end_date: '2026-06-16',
            all_day: true,
            start_time: null,
            end_time: null,
            timezone: 'UTC',
            repeat: 'none',
            repeat_until: null,
            counts_as_leave: true,
            label_vertical: false,
            reminders: [],
            version: 1,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
          leave_impact: [
            { year: 2026, days: 1, remaining_before: 0, remaining_after: -1, exceeds: true },
          ],
        },
      }),
    );
    renderApp();
    const dialog = await openEditor();
    await userEvent.type(within(dialog).getByLabelText('Title'), 'Trip');
    await userEvent.selectOptions(within(dialog).getByLabelText('Category'), 'Vacation');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(/Vacation balance exceeded: 1 day over in 2026/)).toBeVisible();
  });
});

describe('settings › vacation', () => {
  it('PUTs the policy on blur and says Saved', async () => {
    const api = mockApi(
      routes({
        'GET /api/v1/me': ME,
        'GET /api/v1/settings/email': { configured: false, from_address: null },
        'PUT /api/v1/leave/policies/2026': (call) => ({
          year: 2026,
          version: 1,
          ...(call.body as object),
        }),
      }),
    );
    renderApp('/settings');
    const allowance = await screen.findByLabelText('Allowance (days)');
    await userEvent.clear(allowance);
    await userEvent.type(allowance, '22.5');
    await userEvent.tab();
    await waitFor(() => expect(api.callsTo('PUT', '/api/v1/leave/policies/2026')).toHaveLength(1));
    expect(api.callsTo('PUT', '/api/v1/leave/policies/2026')[0]?.body).toEqual({
      allowance_days: 22.5,
      carried_over_days: 2,
    });
    expect(await screen.findByText('Saved')).toBeInTheDocument();
    expect(
      screen.getByText(/use working days, excluding weekends and enabled holidays/),
    ).toBeInTheDocument();
  });
});
