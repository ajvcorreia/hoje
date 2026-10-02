import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, renderApp } from '../../../test/utils';

const WORK = 'aaaaaaaa-0000-0000-0000-000000000001';
const HOME = 'aaaaaaaa-0000-0000-0000-000000000002';

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
  {
    id: HOME,
    name: 'Home',
    colour: 'pink',
    icon: null,
    sort_order: 1,
    is_leave: false,
    hidden: false,
    version: 1,
  },
];

function makeEvent(id: string, title: string, start: string, end = start, extra = {}) {
  return {
    id,
    category_id: WORK,
    title,
    notes: null,
    start_date: start,
    end_date: end,
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
    ...extra,
  };
}

const occurrence = (event: ReturnType<typeof makeEvent>) => ({
  event_id: event.id,
  occurrence_start: event.start_date,
  occurrence_end: event.end_date,
  event,
});

function baseRoutes(events: ReturnType<typeof makeEvent>[] = []) {
  return {
    'GET /api/v1/auth/state': authState({ user: { ...ME, last_category_id: WORK } }),
    'GET /api/v1/categories': CATEGORIES,
    'GET /api/v1/events': { occurrences: events.map(occurrence) },
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

describe('mobile calendar', () => {
  it('renders the mobile day view below 768 px, not the desktop grid', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();
    expect(screen.getByRole('heading', { name: 'Friday, 2 October' })).toBeInTheDocument();
    expect(document.querySelector('[data-month]')).toBeNull();
    expect(document.querySelectorAll('[data-date]').length).toBeLessThanOrEqual(7);
  });

  it('week strip: Mon-Sun, today marked, dots on days with events, paging requests new ranges', async () => {
    const api = mockApi(
      baseRoutes([
        makeEvent('e1', 'Standup', '2026-10-01'),
        makeEvent('e2', 'Dentist', '2026-10-02'),
      ]),
    );
    renderApp();
    await dayViewReady();
    const strip = screen.getByRole('list', { name: 'Week' });
    const buttons = within(strip).getAllByRole('button');
    expect(buttons.map((b) => b.getAttribute('data-date'))).toEqual([
      '2026-09-28',
      '2026-09-29',
      '2026-09-30',
      '2026-10-01',
      '2026-10-02',
      '2026-10-03',
      '2026-10-04',
    ]);
    expect(day('2026-10-02')).toHaveAttribute('aria-current', 'date');
    expect(day('2026-10-01')).not.toHaveAttribute('aria-current');
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Thursday 1 October, 1 event' }),
      ).toBeInTheDocument(),
    );
    expect(within(day('2026-10-01') as HTMLElement).getAllByTestId('week-dot')).toHaveLength(1);
    expect(within(day('2026-09-29') as HTMLElement).queryByTestId('week-dot')).toBeNull();

    expect(api.callsTo('GET', '/api/v1/events')[0]?.search).toContain('from=2026-09-21');
    await userEvent.click(screen.getByRole('button', { name: 'Next week' }));
    expect(day('2026-10-05')).not.toBeNull();
    await waitFor(() =>
      expect(
        api.callsTo('GET', '/api/v1/events').some((c) => c.search.includes('from=2026-09-28')),
      ).toBe(true),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Previous week' }));
    await userEvent.click(screen.getByRole('button', { name: 'Previous week' }));
    expect(day('2026-09-21')).not.toBeNull();
    await waitFor(() =>
      expect(
        api.callsTo('GET', '/api/v1/events').some((c) => c.search.includes('from=2026-09-14')),
      ).toBe(true),
    );
  });

  it('lists all-day events first, then timed ones by start time; multi-day shows Day N of M', async () => {
    mockApi(
      baseRoutes([
        makeEvent('t2', 'Lunch', '2026-10-02', '2026-10-02', {
          all_day: false,
          start_time: '12:30:00',
          end_time: '13:30:00',
        }),
        makeEvent('t1', 'Gym', '2026-10-02', '2026-10-02', {
          all_day: false,
          start_time: '08:00:00',
          end_time: '09:00:00',
        }),
        makeEvent('a1', 'Trip', '2026-10-01', '2026-10-03', { category_id: HOME }),
      ]),
    );
    renderApp();
    const list = await screen.findByRole('list', { name: /Events on 2026-10-02/ });
    await waitFor(() => expect(within(list).getAllByRole('button')).toHaveLength(3));
    const cards = within(list).getAllByRole('button');
    expect(cards.map((c) => c.querySelector('span')?.textContent)).toEqual([
      'Trip',
      'Gym',
      'Lunch',
    ]);
    expect(cards[0]).toHaveTextContent('Home · All day · Day 2 of 3');
    expect(cards[1]).toHaveTextContent('Work · 08:00–09:00');
  });

  it('month view: at most three dots per date; tapping a date lists its events below', async () => {
    const events = Array.from({ length: 5 }, (_, i) =>
      makeEvent(`m${i}`, `Thing ${i}`, '2026-10-15'),
    );
    mockApi(baseRoutes(events));
    renderApp();
    await dayViewReady();
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());
    expect(document.querySelectorAll('[data-date]')).toHaveLength(31);
    expect(day('2026-10-17')).toHaveAttribute('aria-label', 'Saturday 17 October, 0 events');
    await waitFor(() => expect(day('2026-10-15')?.querySelectorAll('.m-dot')).toHaveLength(3));
    expect(day('2026-10-02')).toHaveAttribute('aria-current', 'date');

    await userEvent.click(day('2026-10-15') as HTMLElement);
    const list = await screen.findByRole('list', { name: 'Events on 2026-10-15' });
    expect(within(list).getAllByRole('button')).toHaveLength(5);
    expect(screen.getByRole('heading', { name: 'Thursday, 15 October' })).toBeInTheDocument();
  });

  it('the + button opens a quick add that creates an all-day event on the selected date', async () => {
    const api = mockApi({
      ...baseRoutes(),
      'POST /api/v1/events': (call) => ({
        event: makeEvent('new-1', (call.body as { title: string }).title, '2026-10-03'),
        leave_impact: [],
      }),
    });
    renderApp();
    await dayViewReady();
    await userEvent.click(day('2026-10-03') as HTMLElement);
    await userEvent.click(screen.getByRole('button', { name: 'Add event' }));
    const dialog = await screen.findByRole('dialog');
    const input = within(dialog).getByLabelText('Add an event');
    expect(input).toHaveFocus();
    expect(within(dialog).getByRole('button', { name: 'More' })).toBeInTheDocument();
    await userEvent.type(input, 'Call mum{Enter}');
    await waitFor(() => expect(api.callsTo('POST', '/api/v1/events')).toHaveLength(1));
    expect(api.callsTo('POST', '/api/v1/events')[0]?.body).toEqual({
      title: 'Call mum',
      start_date: '2026-10-03',
      end_date: '2026-10-03',
      all_day: true,
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('More opens the full editor as a sheet', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();
    await userEvent.click(screen.getByRole('button', { name: 'Add event' }));
    await userEvent.click(await screen.findByRole('button', { name: 'More' }));
    expect(await screen.findByRole('dialog', { name: 'New event' })).toBeInTheDocument();
  });

  it('remembers the Day/Month view across remounts', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    expect(window.localStorage.getItem('hoje.calendar.mobileView')).toBe('month');
    cleanup();
    renderApp();
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());
    expect(screen.getByRole('button', { name: 'Month' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('still works when localStorage throws', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());
  });
});
