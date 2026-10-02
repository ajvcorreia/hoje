import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { storeMultidayLabelMode } from '../../lib/multidayLabels';
import { ME, authState, mockApi, renderApp } from '../../test/utils';

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
    version: 3,
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

async function gridReady() {
  await waitFor(() => expect(document.querySelector('[data-month="11"]')).not.toBeNull());
}

function cell(date: string): HTMLElement {
  const el = document.querySelector<HTMLElement>(`[data-date="${date}"]`);
  if (!el) throw new Error(`no cell for ${date}`);
  return el;
}

beforeEach(() => {
  // Only Date is faked so timers, promises and Testing Library polling keep working.
  vi.useFakeTimers({ toFake: ['Date'], now: new Date(2026, 5, 15, 12) });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('month grid', () => {
  it('renders 12 months with day 1 on its weekday row', async () => {
    mockApi(baseRoutes());
    renderApp();
    await gridReady();
    for (let m = 0; m < 12; m += 1) {
      const name = new Date(2026, m, 1).toLocaleString('en-US', { month: 'long' });
      expect(document.querySelector(`[aria-label="${name} 2026"]`)).not.toBeNull();
    }
    // Monday-first rows: Thu 1 Jan 2026 -> row 3, Sun 1 Feb -> row 6, Mon 1 Jun -> row 0.
    expect(cell('2026-01-01')).toHaveAttribute('data-row', '3');
    expect(cell('2026-02-01')).toHaveAttribute('data-row', '6');
    expect(cell('2026-06-01')).toHaveAttribute('data-row', '0');
    expect(cell('2026-01-31')).toHaveAttribute('data-row', '33');
    expect(document.querySelectorAll('[data-month="1"] [data-date]')).toHaveLength(28);
    expect(document.querySelectorAll('[data-month="0"] .cal-empty')).toHaveLength(37 - 31);
  });

  it('shades weekend rows from the user settings', async () => {
    mockApi(baseRoutes());
    renderApp();
    await gridReady();
    expect(cell('2026-01-03')).toHaveAttribute('data-weekend', 'true'); // Saturday
    expect(cell('2026-01-04')).toHaveAttribute('data-weekend', 'true'); // Sunday
    expect(cell('2026-01-05')).not.toHaveAttribute('data-weekend'); // Monday
    // The whole row, including empty cells of other months, is shaded.
    const emptyOnSundayRow = document.querySelector('[data-month="0"] .cal-empty[data-row="34"]');
    expect(emptyOnSundayRow).toHaveAttribute('data-weekend', 'true');
    expect(cell('2026-06-15')).toHaveAttribute('data-today', 'true');
  });

  it('opens a popover with focus in the type-to-add field and creates an all-day event', async () => {
    const api = mockApi({
      ...baseRoutes(),
      'POST /api/v1/events': (call) => ({
        event: makeEvent('new-1', (call.body as { title: string }).title, '2026-01-01'),
        leave_impact: [],
      }),
    });
    renderApp();
    await gridReady();
    await userEvent.click(cell('2026-01-01'));

    const popover = await screen.findByRole('dialog', {
      hidden: true,
      name: /Events on Thursday 1 January/,
    });
    const input = within(popover).getByLabelText('Add an event');
    expect(input).toHaveFocus();
    expect(within(popover).getByText('No events')).toBeInTheDocument();

    await userEvent.type(input, 'Dentist{Enter}');
    await waitFor(() => expect(api.callsTo('POST', '/api/v1/events')).toHaveLength(1));
    expect(api.callsTo('POST', '/api/v1/events')[0]?.body).toEqual({
      title: 'Dentist',
      start_date: '2026-01-01',
      end_date: '2026-01-01',
      all_day: true,
    });
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { hidden: true })).not.toBeInTheDocument(),
    );
  });

  it('closes the popover with Escape', async () => {
    mockApi(baseRoutes());
    renderApp();
    await gridReady();
    await userEvent.click(cell('2026-01-01'));
    await screen.findByRole('dialog', { hidden: true });
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { hidden: true })).not.toBeInTheDocument();
    expect(cell('2026-01-01')).toHaveFocus();
  });

  it('moves focus between day cells with the arrow keys', async () => {
    mockApi(baseRoutes());
    renderApp();
    await gridReady();
    cell('2026-01-05').focus();
    await userEvent.keyboard('{ArrowDown}');
    expect(cell('2026-01-06')).toHaveFocus();
    expect(cell('2026-01-06')).toHaveAttribute('tabindex', '0');
    expect(cell('2026-01-05')).toHaveAttribute('tabindex', '-1');
    await userEvent.keyboard('{ArrowRight}');
    expect(cell('2026-02-03')).toHaveFocus();
  });

  it('splits a cell in two halves for two events and adds +1 for a third', async () => {
    mockApi(
      baseRoutes([
        makeEvent('e1', 'Alpha', '2026-03-10'),
        makeEvent('e2', 'Beta', '2026-03-10'),
        makeEvent('e3', 'Gamma', '2026-03-11'),
        makeEvent('e4', 'Delta', '2026-03-11'),
        makeEvent('e5', 'Epsilon', '2026-03-11'),
        makeEvent('e6', 'Solo', '2026-03-12'),
      ]),
    );
    renderApp();
    await waitFor(() => expect(within(cell('2026-03-12')).getByText('Solo')).toBeInTheDocument());

    expect(cell('2026-03-10').querySelectorAll('[data-half]')).toHaveLength(2);
    expect(within(cell('2026-03-10')).queryByText(/^\+\d/)).not.toBeInTheDocument();

    expect(cell('2026-03-11').querySelectorAll('[data-half]')).toHaveLength(2);
    expect(within(cell('2026-03-11')).getByText('+1')).toBeInTheDocument();

    const solo = cell('2026-03-12').querySelectorAll('.cal-ev');
    expect(solo).toHaveLength(1);
    expect(solo[0]).toHaveAttribute('data-lane', 'full');
  });

  it('draws a multi-day event as a block with one title per month column', async () => {
    mockApi(baseRoutes([makeEvent('trip', 'Trip', '2026-03-30', '2026-04-02')]));
    renderApp();
    await waitFor(() => expect(within(cell('2026-03-30')).getByText('Trip')).toBeInTheDocument());
    expect(within(cell('2026-03-31')).queryByText('Trip')).not.toBeInTheDocument();
    expect(cell('2026-03-31').querySelector('.cal-ev')).not.toBeNull();
    expect(within(cell('2026-04-01')).getByText('Trip')).toBeInTheDocument();
    expect(within(cell('2026-04-02')).queryByText('Trip')).not.toBeInTheDocument();
    expect(cell('2026-03-30').querySelector('.cal-ev')).toHaveAttribute('data-join-next', 'true');
    expect(cell('2026-04-02').querySelector('.cal-ev')).not.toHaveAttribute('data-join-next');
  });
});

describe('event editor', () => {
  it('keeps the More section collapsed until opened', async () => {
    mockApi(baseRoutes());
    renderApp();
    await gridReady();
    await userEvent.click(cell('2026-01-01'));
    await userEvent.click(
      await screen.findByRole('button', { hidden: true, name: 'Add with details' }),
    );

    const dialog = await screen.findByRole('dialog', { hidden: true, name: 'New event' });
    expect(within(dialog).getByLabelText('Title')).toHaveFocus();
    // The last used category is preselected.
    expect(within(dialog).getByLabelText('Category')).toHaveValue(WORK);
    const more = within(dialog).getByRole('button', { name: 'More' });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    expect(within(dialog).queryByLabelText('Start date')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Reminder')).not.toBeInTheDocument();

    await userEvent.click(more);
    expect(within(dialog).getByLabelText('Start date')).toHaveValue('2026-01-01');
    expect(within(dialog).getByLabelText('Reminder')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Repeat')).toBeInTheDocument();
  });

  it('deletes with an undo toast; Undo restores the event', async () => {
    const event = makeEvent('ev-1', 'Dentist', '2026-01-08');
    const api = mockApi({
      ...baseRoutes([event]),
      'GET /api/v1/events/ev-1': event,
      'DELETE /api/v1/events/ev-1': null,
      'POST /api/v1/events/ev-1/restore': event,
    });
    renderApp();
    await waitFor(() =>
      expect(within(cell('2026-01-08')).getByText('Dentist')).toBeInTheDocument(),
    );
    await userEvent.click(cell('2026-01-08'));
    const popover = await screen.findByRole('dialog', { hidden: true, name: /Events on/ });
    expect(within(popover).getByText('Work')).toBeInTheDocument(); // category name, not just colour
    await userEvent.click(within(popover).getByRole('button', { name: /Dentist/ }));

    const editor = await screen.findByRole('dialog', { hidden: true, name: 'Edit event' });
    await within(editor).findByDisplayValue('Dentist');
    await userEvent.click(within(editor).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(api.callsTo('DELETE', '/api/v1/events/ev-1')).toHaveLength(1));
    expect(await screen.findByText('Event deleted')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { hidden: true, name: 'Undo' }));
    await waitFor(() => expect(api.callsTo('POST', '/api/v1/events/ev-1/restore')).toHaveLength(1));
  });

  it('shows the conflict notice on 409 and can reload the server copy', async () => {
    const event = makeEvent('ev-2', 'Review', '2026-01-09');
    const current = { ...event, title: 'Review (moved)', version: 2 };
    const api = mockApi({
      ...baseRoutes([event]),
      'GET /api/v1/events/ev-2': event,
      'PATCH /api/v1/events/ev-2': () =>
        new Response(
          JSON.stringify({ title: 'Conflict', status: 409, detail: 'Version mismatch', current }),
          { status: 409, headers: { 'content-type': 'application/problem+json' } },
        ),
    });
    renderApp();
    await waitFor(() => expect(within(cell('2026-01-09')).getByText('Review')).toBeInTheDocument());
    await userEvent.click(cell('2026-01-09'));
    await userEvent.click(await screen.findByRole('button', { hidden: true, name: /Review/ }));

    const editor = await screen.findByRole('dialog', { hidden: true, name: 'Edit event' });
    const title = await within(editor).findByDisplayValue('Review');
    await userEvent.type(title, ' edited');
    await userEvent.click(within(editor).getByRole('button', { name: 'Save' }));

    expect(
      await within(editor).findByText('This event was changed elsewhere.'),
    ).toBeInTheDocument();
    expect(api.callsTo('PATCH', '/api/v1/events/ev-2')[0]?.body).toMatchObject({
      title: 'Review edited',
      version: 1,
    });

    await userEvent.click(within(editor).getByRole('button', { name: 'Reload' }));
    expect(within(editor).getByDisplayValue('Review (moved)')).toBeInTheDocument();
    expect(within(editor).queryByText('This event was changed elsewhere.')).not.toBeInTheDocument();
  });
});

describe('category chips', () => {
  it('toggle the hidden flag through PATCH /categories', async () => {
    // Stateful like the real server: the refetch after the mutation must see the change.
    let categories = [...CATEGORIES];
    const api = mockApi({
      ...baseRoutes(),
      'GET /api/v1/categories': () => categories,
      'PATCH /api/v1/categories/aaaaaaaa-0000-0000-0000-000000000002': (call) => {
        const updated = { ...CATEGORIES[1]!, ...(call.body as object), version: 4 };
        categories = categories.map((c) => (c.id === updated.id ? updated : c));
        return updated;
      },
    });
    renderApp();
    const chips = await screen.findByRole('group', { hidden: true, name: 'Show categories' });
    const home = await within(chips).findByRole('button', { name: 'Home' });
    expect(home).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(home);
    await waitFor(() =>
      expect(
        api.callsTo('PATCH', '/api/v1/categories/aaaaaaaa-0000-0000-0000-000000000002'),
      ).toHaveLength(1),
    );
    expect(
      api.callsTo('PATCH', '/api/v1/categories/aaaaaaaa-0000-0000-0000-000000000002')[0]?.body,
    ).toEqual({ hidden: true, version: 3 });
    await waitFor(() => expect(home).toHaveAttribute('aria-pressed', 'false'));
  });

  it('hides events of a hidden category', async () => {
    const hidden = [CATEGORIES[0], { ...CATEGORIES[1], hidden: true }];
    mockApi({
      ...baseRoutes([
        makeEvent('w', 'Work thing', '2026-03-10'),
        makeEvent('h', 'Home thing', '2026-03-11', '2026-03-11', { category_id: HOME }),
      ]),
      'GET /api/v1/categories': hidden,
    });
    renderApp();
    await waitFor(() =>
      expect(within(cell('2026-03-10')).getByText('Work thing')).toBeInTheDocument(),
    );
    expect(screen.queryByText('Home thing')).not.toBeInTheDocument();
  });
});

describe('views', () => {
  it('switches to the year view and the agenda', async () => {
    mockApi(
      baseRoutes([makeEvent('a', 'Alpha', '2026-07-01'), makeEvent('b', 'Beta', '2026-07-01')]),
    );
    renderApp();
    await gridReady();
    await userEvent.click(screen.getByRole('button', { hidden: true, name: 'Year' }));
    const july = await screen.findByRole('region', { hidden: true, name: 'July 2026' });
    await waitFor(() =>
      expect(
        within(july).getByRole('button', { name: /Wednesday 1 July 2026, 2 events/ }),
      ).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole('button', { hidden: true, name: 'Agenda' }));
    expect(await screen.findByText('Alpha')).toBeInTheDocument();
    expect(screen.getAllByText('Work', { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { hidden: true, name: 'Load more' })).toBeInTheDocument();
  });
});

describe('vertical multi-day labels', () => {
  afterEach(() => {
    storeMultidayLabelMode('horizontal');
  });

  const labels = () => Array.from(document.querySelectorAll<HTMLElement>('.cal-vlabel'));

  it('renders one rotated label per block with the block height and no horizontal title', async () => {
    storeMultidayLabelMode('vertical');
    mockApi(baseRoutes([makeEvent('trip', 'Trip', '2026-03-10', '2026-03-13')]));
    renderApp();
    await waitFor(() => expect(labels()).toHaveLength(1));
    const label = labels()[0] as HTMLElement;
    expect(label).toHaveTextContent('Trip');
    expect(label).toHaveAttribute('aria-hidden', 'true');
    expect(label).toHaveAttribute('data-lane', 'full');
    expect(label.style.getPropertyValue('--seg-len')).toBe('4');
    expect(label.style.getPropertyValue('--seg-row')).toBe(
      cell('2026-03-10').getAttribute('data-row'),
    );
    expect(label.closest('[data-month]')).toHaveAttribute('data-month', '2');
    // The cells keep their blocks but no longer carry the truncated horizontal title.
    expect(cell('2026-03-10').querySelector('.cal-ev')).toHaveTextContent('');
    expect(cell('2026-03-10').querySelector('.cal-ev')).toHaveAttribute('data-join-next', 'true');
  });

  it('starts a new segment in the next month column', async () => {
    storeMultidayLabelMode('vertical');
    mockApi(baseRoutes([makeEvent('trip', 'Trip', '2026-03-30', '2026-04-02')]));
    renderApp();
    await waitFor(() => expect(labels()).toHaveLength(2));
    expect(labels().map((l) => l.style.getPropertyValue('--seg-len'))).toEqual(['2', '2']);
    expect(labels().map((l) => l.closest('[data-month]')?.getAttribute('data-month'))).toEqual([
      '2',
      '3',
    ]);
  });

  it('puts the label in the lane of a split block', async () => {
    storeMultidayLabelMode('vertical');
    mockApi(
      baseRoutes([
        makeEvent('trip', 'Trip', '2026-03-10', '2026-03-12'),
        makeEvent('other', 'Other', '2026-03-10', '2026-03-12'),
      ]),
    );
    renderApp();
    await waitFor(() => expect(labels()).toHaveLength(2));
    expect(labels().map((l) => l.getAttribute('data-lane'))).toEqual(['0', '1']);
  });

  it('leaves single-day events and horizontal mode unchanged', async () => {
    storeMultidayLabelMode('vertical');
    mockApi(
      baseRoutes([
        makeEvent('solo', 'Solo', '2026-03-05'),
        makeEvent('trip', 'Trip', '2026-03-10', '2026-03-12'),
      ]),
    );
    renderApp();
    await waitFor(() => expect(within(cell('2026-03-05')).getByText('Solo')).toBeInTheDocument());
    expect(labels()).toHaveLength(1);
    act(() => storeMultidayLabelMode('horizontal'));
    await waitFor(() => expect(labels()).toHaveLength(0));
    expect(within(cell('2026-03-10')).getByText('Trip')).toBeInTheDocument();
  });
});
