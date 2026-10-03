import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, renderApp } from '../../test/utils';

const WORK = 'aaaaaaaa-0000-0000-0000-000000000001';
const PT = 'cccccccc-0000-0000-0000-000000000001';
const AE = 'cccccccc-0000-0000-0000-000000000002';

const CALENDARS = [
  { id: PT, code: 'PT', name: 'Portugal', enabled: true, colour: 'green', holiday_count: 3 },
  {
    id: AE,
    code: 'AE',
    name: 'United Arab Emirates',
    enabled: false,
    colour: 'red',
    holiday_count: 1,
  },
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
  holiday('h1', '2026-04-25', 'Freedom Day'),
  holiday('h2', '2026-12-25', 'Christmas Day'),
  holiday('h3', '2026-03-20', 'Eid Estimate', { estimated: true, is_non_working: false }),
];

function event(id: string, title: string, date: string) {
  return {
    id,
    category_id: WORK,
    title,
    notes: null,
    start_date: date,
    end_date: date,
    all_day: true,
    start_time: null,
    end_time: null,
    timezone: 'UTC',
    repeat: 'none',
    repeat_until: null,
    counts_as_leave: false,
    label_vertical: false,
    reminders: [],
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function routes(
  events: ReturnType<typeof event>[] = [],
  extra: Parameters<typeof mockApi>[0] = {},
) {
  return {
    'GET /api/v1/auth/state': authState({ user: { ...ME, last_category_id: WORK } }),
    'GET /api/v1/categories': [
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
    ],
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
    ...extra,
  } as Parameters<typeof mockApi>[0];
}

function cell(date: string): HTMLElement {
  const el = document.querySelector<HTMLElement>(`[data-date="${date}"]`);
  if (!el) throw new Error(`no cell for ${date}`);
  return el;
}

// The full 12-month grid (with text measuring) is slow to mount under a loaded test run.
const holidaysDrawn = () =>
  waitFor(() => expect(document.querySelector('.cal-hol')).not.toBeNull(), { timeout: 5000 });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: new Date(2026, 5, 15, 12) });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('holiday overlays', () => {
  it('fills the event area of an empty day with the calendar colour and name', async () => {
    mockApi(routes());
    renderApp();
    await holidaysDrawn();
    const hol = cell('2026-04-25').querySelector('.cal-hol');
    expect(hol).toHaveTextContent('Freedom Day');
    expect(hol).toHaveAttribute('data-cat', 'green');
    expect(cell('2026-04-25')).toHaveAccessibleName(/holiday: Freedom Day/);
  });

  it('only marks the corner of a day that has events', async () => {
    mockApi(routes([event('e1', 'Party', '2026-12-25')]));
    renderApp();
    await holidaysDrawn();
    const day = cell('2026-12-25');
    expect(day.querySelector('.cal-hol')).toBeNull();
    expect(day.querySelector('.cal-hol-mark')).toHaveAttribute('data-cat', 'green');
    expect(day.querySelector('.cal-ev')).toHaveTextContent('Party');
  });

  it('shades non-working holidays like a weekend and leaves working ones alone', async () => {
    mockApi(routes());
    renderApp();
    await holidaysDrawn();
    expect(cell('2026-12-25')).toHaveAttribute('data-holiday-off', 'true');
    expect(cell('2026-03-20')).not.toHaveAttribute('data-holiday-off');
  });

  it('lists the day holidays first in the popover, marking estimated ones', async () => {
    mockApi(routes([event('e1', 'Standup', '2026-03-20')]));
    renderApp();
    await holidaysDrawn();
    await userEvent.click(cell('2026-03-20'));
    const popover = await screen.findByRole('dialog', { hidden: true, name: /Events on/ });
    const list = within(popover).getByRole('list', { hidden: true, name: 'Holidays' });
    expect(list).toHaveTextContent('Portugal · Eid Estimate (estimated)');
    const lists = popover.querySelectorAll('ul');
    expect(lists[0]).toBe(list);
  });

  it('hides the overlays with the Holidays chip', async () => {
    mockApi(routes());
    renderApp();
    await holidaysDrawn();
    const chip = screen.getByRole('button', { name: 'Holidays' });
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    expect(document.querySelector('.cal-hol')).toBeNull();
  });
});

describe('settings › holidays', () => {
  const settings = (extra: Parameters<typeof mockApi>[0] = {}) =>
    routes([], {
      'GET /api/v1/me': ME,
      'GET /api/v1/settings/email': { configured: false, from_address: null },
      [`GET /api/v1/holiday-calendars/${PT}/holidays`]: HOLIDAYS.filter(
        (h) => h.date >= '2026-01-01',
      ),
      ...extra,
    });

  it('PATCHes the enabled flag and colour of a calendar', async () => {
    const api = mockApi(
      settings({ [`PATCH /api/v1/holiday-calendars/${AE}`]: { ...CALENDARS[1], enabled: true } }),
    );
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('checkbox', { name: 'United Arab Emirates' }));
    await waitFor(() =>
      expect(api.callsTo('PATCH', `/api/v1/holiday-calendars/${AE}`)).toHaveLength(1),
    );
    expect(api.callsTo('PATCH', `/api/v1/holiday-calendars/${AE}`)[0]?.body).toEqual({
      enabled: true,
    });
    expect(
      screen.getByText('Islamic holidays are estimates; check official announcements.'),
    ).toBeInTheDocument();
    const picker = screen.getByRole('radiogroup', { name: 'Colour for Portugal holidays' });
    await userEvent.click(within(picker).getByRole('radio', { name: 'Blue' }));
    await waitFor(() =>
      expect(api.callsTo('PATCH', `/api/v1/holiday-calendars/${PT}`)).toHaveLength(1),
    );
    expect(api.callsTo('PATCH', `/api/v1/holiday-calendars/${PT}`)[0]?.body).toEqual({
      colour: 'blue',
    });
  });

  it('edits, deletes and adds holidays and resets the calendar', async () => {
    const api = mockApi(
      settings({
        'PATCH /api/v1/holidays/h1': {},
        'DELETE /api/v1/holidays/h2': null,
        [`POST /api/v1/holiday-calendars/${PT}/holidays`]: {},
        [`POST /api/v1/holiday-calendars/${PT}/reset`]: CALENDARS[0] ?? {},
      }),
    );
    renderApp('/settings');
    await userEvent.click(
      (await screen.findAllByRole('button', { name: /Edit holidays/ }))[0] as HTMLElement,
    );
    const name = await screen.findByLabelText('Name of holiday on 2026-04-25');
    expect(screen.getByText('(estimated)')).toBeInTheDocument();
    await userEvent.clear(name);
    await userEvent.type(name, 'Liberty Day{Enter}');
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/holidays/h1')).toHaveLength(1));
    expect(api.callsTo('PATCH', '/api/v1/holidays/h1')[0]?.body).toEqual({ name: 'Liberty Day' });

    await userEvent.click(screen.getByRole('checkbox', { name: /Non-working 2026-03-20/ }));
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/holidays/h3')).toHaveLength(1));
    expect(api.callsTo('PATCH', '/api/v1/holidays/h3')[0]?.body).toEqual({ is_non_working: true });

    await userEvent.click(screen.getByRole('button', { name: 'Delete Christmas Day' }));
    await waitFor(() => expect(api.callsTo('DELETE', '/api/v1/holidays/h2')).toHaveLength(1));

    await userEvent.type(screen.getByLabelText('Date'), '2026-06-10');
    await userEvent.type(screen.getByLabelText('Name'), 'City Day');
    await userEvent.click(screen.getByRole('button', { name: 'Add holiday' }));
    const add = `/api/v1/holiday-calendars/${PT}/holidays`;
    await waitFor(() => expect(api.callsTo('POST', add)).toHaveLength(1));
    expect(api.callsTo('POST', add)[0]?.body).toEqual({
      date: '2026-06-10',
      name: 'City Day',
      is_non_working: true,
    });

    await userEvent.click(screen.getByRole('button', { name: 'Reset to defaults' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent(
      'This removes your changes and added holidays for this calendar',
    );
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reset' }));
    await waitFor(() =>
      expect(api.callsTo('POST', `/api/v1/holiday-calendars/${PT}/reset`)).toHaveLength(1),
    );
  });
});

describe('fit columns to text', () => {
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
      () =>
        ({
          font: '',
          measureText: (text: string) => ({ width: text.length * 6 }),
        }) as unknown as CanvasRenderingContext2D,
    );
  });
  afterEach(() => vi.restoreAllMocks());

  const longTitle = 'A very long event title that would normally be truncated by the grid';
  const fitOf = (month: number) =>
    parseFloat(
      document
        .querySelector<HTMLElement>(`[data-month="${month}"]`)
        ?.style.getPropertyValue('--col-fit') ?? 'NaN',
    );

  it('gives a month with a long title a larger --col-fit and no ellipsis', async () => {
    mockApi(routes([event('e1', longTitle, '2026-01-10')], { 'GET /api/v1/holidays': [] }));
    renderApp();
    await waitFor(() => expect(fitOf(0)).toBeGreaterThan(0));
    expect(fitOf(0)).toBeGreaterThan(longTitle.length * 6);
    expect(fitOf(1)).toBe(0);
    const grid = document.querySelector<HTMLElement>('.cal-grid');
    // Every month: lead + max(three day-number widths, widest text).
    expect(grid?.style.gridTemplateColumns).toContain('max(3 * var(--num-w), 0px)');
    expect(cell('2026-01-10').querySelector('.cal-ev')).toHaveTextContent(longTitle);
  });

  it('gives months without any text the three-day-number minimum', async () => {
    mockApi(routes([], { 'GET /api/v1/holidays': [] }));
    renderApp();
    await waitFor(() => expect(fitOf(0)).toBe(0));
    const template = document.querySelector<HTMLElement>('.cal-grid')?.style.gridTemplateColumns;
    expect(template?.match(/max\(3 \* var\(--num-w\), 0px\)/g)).toHaveLength(12);
  });
});
