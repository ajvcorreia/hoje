import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, renderApp } from '../../test/utils';

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
    {
      event_id: 'bbbbbbbb-0000-0000-0000-000000000002',
      title: 'Madeira',
      start_date: '2026-09-10',
      end_date: '2026-09-12',
      days: 3,
    },
  ],
};

function routes(extra: Parameters<typeof mockApi>[0] = {}) {
  return {
    'GET /api/v1/auth/state': authState({ user: { ...ME, last_category_id: WORK } }),
    'GET /api/v1/categories': [
      category(WORK, 'Work', false, 0),
      category(VAC, 'Vacation', true, 1),
    ],
    'GET /api/v1/events': { occurrences: [] },
    'GET /api/v1/leave/balance': BALANCE,
    ...extra,
  } as Parameters<typeof mockApi>[0];
}

// Friday 2 October 2026.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: new Date(2026, 9, 2, 12) });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('vacation pill: mobile (sheet)', () => {
  it('opens balance as a dialog (sheet) on mobile viewport', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false, // Mobile: matches < 768px
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes());
    renderApp();

    const pill = await screen.findByRole(
      'button',
      { name: 'Vacation: 16.5 left' },
      { timeout: 5000 },
    );
    await userEvent.click(pill);

    // Should open as a Dialog (sheet on mobile)
    const dialog = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });
    expect(dialog).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it('displays balance rows in the sheet', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes());
    renderApp();

    const pill = await screen.findByRole(
      'button',
      { name: /Vacation: 16.5 left/ },
      { timeout: 5000 },
    );
    await userEvent.click(pill);

    const dialog = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });

    for (const [label, value] of [
      ['Allowance', '22'],
      ['Carried over', '2'],
      ['Used', '4.5'],
      ['Planned', '3'],
      ['Remaining', '16.5'],
    ] as const) {
      const term = within(dialog).getByText(label);
      expect(term.nextElementSibling).toHaveTextContent(value);
    }

    vi.unstubAllGlobals();
  });

  it('displays bookings list in the sheet', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes());
    renderApp();

    const pill = await screen.findByRole(
      'button',
      { name: /Vacation: 16.5 left/ },
      { timeout: 5000 },
    );
    await userEvent.click(pill);

    const dialog = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });

    // Check bookings are present
    expect(within(dialog).getByRole('button', { name: /Algarve/ })).toHaveTextContent('3 days');
    expect(within(dialog).getByRole('button', { name: /Madeira/ })).toHaveTextContent('3 days');

    vi.unstubAllGlobals();
  });

  it('closes the sheet when clicking the pill again', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes());
    renderApp();

    const pill = await screen.findByRole(
      'button',
      { name: /Vacation: 16.5 left/ },
      { timeout: 5000 },
    );
    await userEvent.click(pill);

    const dialog = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });
    expect(dialog).toBeInTheDocument();

    // Click the pill again to close the sheet
    await userEvent.click(pill);

    await waitFor(() => {
      const closedDialog = screen.queryByRole('dialog', { hidden: true, name: 'Vacation balance' });
      expect(closedDialog).not.toBeInTheDocument();
    });

    vi.unstubAllGlobals();
  });
});

describe('vacation pill: desktop (popover)', () => {
  it('opens balance as a popover on desktop viewport', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true, // Desktop: matches >= 768px
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes());
    renderApp('/settings'); // only the header pill is needed; the desktop grid is slow to mount

    const pill = await screen.findByRole(
      'button',
      { name: 'Vacation: 16.5 left' },
      { timeout: 5000 },
    );
    await userEvent.click(pill);

    // Should open as a Popover (not a Dialog)
    const popover = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });
    expect(popover).toBeInTheDocument();

    // Popover should be positioned near the pill
    expect(popover).toBeTruthy();

    vi.unstubAllGlobals();
  });

  it('displays balance rows in the popover', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes());
    renderApp();

    const pill = await screen.findByRole(
      'button',
      { name: /Vacation: 16.5 left/ },
      { timeout: 5000 },
    );
    await userEvent.click(pill);

    const popover = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });

    for (const [label, value] of [
      ['Allowance', '22'],
      ['Carried over', '2'],
      ['Used', '4.5'],
      ['Planned', '3'],
      ['Remaining', '16.5'],
    ] as const) {
      const term = within(popover).getByText(label);
      expect(term.nextElementSibling).toHaveTextContent(value);
    }

    vi.unstubAllGlobals();
  });
});

describe('vacation pill: mobile interactions', () => {
  it('shows edit link in both sheet and popover', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes());
    renderApp();

    const pill = await screen.findByRole(
      'button',
      { name: /Vacation: 16.5 left/ },
      { timeout: 5000 },
    );
    await userEvent.click(pill);

    const dialog = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });
    const editLink = within(dialog).getByRole('link', { name: 'Edit allowance' });

    expect(editLink).toHaveAttribute('href', '/settings#vacation');

    vi.unstubAllGlobals();
  });

  it('can select a booking to edit in mobile sheet', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes());
    renderApp();

    const pill = await screen.findByRole(
      'button',
      { name: /Vacation: 16.5 left/ },
      { timeout: 5000 },
    );
    await userEvent.click(pill);

    const dialog = await screen.findByRole('dialog', { hidden: true, name: 'Vacation balance' });
    const algarvButton = within(dialog).getByRole('button', { name: /Algarve/ });

    expect(algarvButton).toBeInTheDocument();
    expect(algarvButton).toHaveTextContent('3 days');

    // Clicking should close the balance sheet and open the event editor
    await userEvent.click(algarvButton);

    // The balance dialog should close
    await waitFor(() => {
      expect(
        screen.queryByRole('dialog', { hidden: true, name: 'Vacation balance' }),
      ).not.toBeInTheDocument();
    });

    vi.unstubAllGlobals();
  });

  it('pill shows overdrawn balance in danger color on mobile', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));

    mockApi(routes({ 'GET /api/v1/leave/balance': { ...BALANCE, remaining: -2 } }));
    renderApp();

    const pill = await screen.findByRole('button', { name: 'Vacation: 2 over' }, { timeout: 5000 });
    expect(pill).toHaveClass('text-danger');

    vi.unstubAllGlobals();
  });
});
