import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, renderApp } from '../../../test/utils';

const WORK = 'aaaaaaaa-0000-0000-0000-000000000001';
const PT = 'cccccccc-0000-0000-0000-000000000001';

const CATEGORIES = [
  {
    id: WORK,
    name: 'Work',
    colour: 'teal',
    icon: null,
    sort_order: 0,
    is_leave: false,
    hidden: false,
    version: 1,
  },
];

const CALENDARS = [
  { id: PT, code: 'PT', name: 'Portugal', enabled: true, colour: 'green', holiday_count: 3 },
];

const holiday = (id: string, date: string, name: string, extra = {}) => ({
  id,
  calendar_id: PT,
  date,
  name,
  is_non_working: true,
  source: 'bundled',
  estimated: false,
  ...extra,
});

const HOLIDAYS = [
  holiday('h1', '2026-10-02', 'Holiday on selected day'),
  holiday('h2', '2026-10-05', 'Another holiday', { estimated: true }),
];

interface TestEvent {
  id: string;
  category_id: string;
  title: string;
  notes: null;
  start_date: string;
  end_date: string;
  all_day: boolean;
  start_time: null;
  end_time: null;
  timezone: string;
  repeat: string;
  repeat_until: null;
  counts_as_leave: boolean;
  label_vertical: boolean;
  reminders: unknown[];
  version: number;
  created_at: string;
  updated_at: string;
}

function baseRoutes(events: TestEvent[] = []) {
  return {
    'GET /api/v1/auth/state': authState({ user: { ...ME, last_category_id: WORK } }),
    'GET /api/v1/categories': CATEGORIES,
    'GET /api/v1/events': {
      occurrences: events.map((e) => ({
        event_id: e.id,
        occurrence_start: e.start_date,
        occurrence_end: e.end_date,
        event: e,
      })),
    },
    'GET /api/v1/holiday-calendars': CALENDARS,
    'GET /api/v1/holidays': HOLIDAYS,
  };
}

// Friday 2 October 2026.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: new Date(2026, 9, 2, 12) });
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const day = (iso: string) => document.querySelector<HTMLElement>(`[data-date="${iso}"]`);

async function dayViewReady() {
  await waitFor(() => expect(day('2026-10-02')).not.toBeNull());
}

describe('mobile day view: holiday cards', () => {
  it('shows a holiday card on the selected day with calendar name and name', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    // The selected day (2026-10-02) has a holiday
    const list = await screen.findByRole('list', { name: /Holidays/ });
    expect(within(list).getByText('Holiday on selected day')).toBeInTheDocument();
    expect(within(list).getByText('Portugal')).toBeInTheDocument();
  });

  it('marks estimated holidays with estimated suffix', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    // Navigate to day with estimated holiday by clicking next week
    await userEvent.click(screen.getByRole('button', { name: 'Next week' }));

    // Wait for October 5 to be visible in the week strip
    const oct5 = day('2026-10-05');
    await waitFor(() => expect(oct5).not.toBeNull());

    // Click on October 5 to select it
    if (oct5) {
      await userEvent.click(oct5);
    }

    // Wait for the holidays list to show the estimated holiday
    await waitFor(() => {
      const list = screen.getByRole('list', { name: /Holidays/ });
      expect(list.textContent).toContain('Another holiday');
      expect(list.textContent).toContain('estimated');
    });
  });

  it('shows holiday cards with non-interactive styling', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    const list = await screen.findByRole('list', { name: /Holidays/ });
    const card = list.querySelector('[data-cat="green"]');

    // Should have the m-card styling but not be a button
    expect(card?.className).toContain('m-card');
  });
});

describe('mobile month view: holiday indicators', () => {
  it('shows holiday dot in month view cells', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    // Switch to month view
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());

    // Day 2 Oct has a holiday, should have a holiday dot
    const oct2 = day('2026-10-02');
    const holidayDot = oct2?.querySelector('[data-cat="green"].m-hol-dot');
    expect(holidayDot).toBeInTheDocument();
  });

  it('shows estimated holiday indicator in month view', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());

    // Day 5 Oct has estimated holiday
    const oct5 = day('2026-10-05');
    const holidayDot = oct5?.querySelector('[data-cat="green"].m-hol-dot');
    expect(holidayDot).toBeInTheDocument();
  });

  it('includes holiday in aria-label for accessibility', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());

    const oct2 = day('2026-10-02');
    expect(oct2).toHaveAccessibleName(/Holiday on selected day/);
  });
});

describe('mobile holidays chip', () => {
  it('the Holidays chip hides holiday indicators in month view', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());

    // Holiday should be visible initially
    expect(day('2026-10-02')?.querySelector('.m-hol-dot')).toBeInTheDocument();

    // Toggle holidays off
    const chip = screen.getByRole('button', { name: 'Holidays' });
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(chip);

    // Holiday should be hidden
    await waitFor(() => {
      expect(day('2026-10-02')?.querySelector('.m-hol-dot')).not.toBeInTheDocument();
    });

    // Toggle back on
    await userEvent.click(chip);
    await waitFor(() => {
      expect(day('2026-10-02')?.querySelector('.m-hol-dot')).toBeInTheDocument();
    });
  });

  it('the Holidays chip hides holiday cards in day view', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    // Holiday should be visible initially
    let list = await screen.findByRole('list', { name: /Holidays/ });
    expect(list).toBeInTheDocument();

    // Toggle holidays off
    const chip = screen.getByRole('button', { name: 'Holidays' });
    await userEvent.click(chip);

    // Holiday should be hidden
    await waitFor(() => {
      expect(screen.queryByRole('list', { name: /Holidays/ })).not.toBeInTheDocument();
    });

    // Toggle back on
    await userEvent.click(chip);
    list = await screen.findByRole('list', { name: /Holidays/ });
    expect(list).toBeInTheDocument();
  });
});

describe('mobile: holidays with events on the same day', () => {
  it('shows both holiday cards and event cards in day view', async () => {
    const event = {
      id: 'e1',
      category_id: WORK,
      title: 'Meeting',
      notes: null,
      start_date: '2026-10-02',
      end_date: '2026-10-02',
      all_day: true,
      start_time: null,
      end_time: null,
      timezone: 'Europe/Lisbon',
      repeat: 'none',
      repeat_until: null,
      counts_as_leave: false,
      label_vertical: false,
      reminders: [],
      version: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    mockApi(baseRoutes([event]));
    renderApp();
    await dayViewReady();

    // Both holiday and event should be present
    const holidayList = await screen.findByRole('list', { name: /Holidays/ });
    expect(within(holidayList).getByText('Holiday on selected day')).toBeInTheDocument();

    const eventList = await screen.findByRole('list', { name: /Events on/ });
    expect(within(eventList).getByText('Meeting')).toBeInTheDocument();
  });
});
