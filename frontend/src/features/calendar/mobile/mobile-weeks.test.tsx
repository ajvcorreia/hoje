import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, renderApp } from '../../../test/utils';
import { storeWeekNumbers } from '../../../lib/weekNumbers';

const WORK = 'aaaaaaaa-0000-0000-0000-000000000001';

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

function baseRoutes() {
  return {
    'GET /api/v1/auth/state': authState({ user: { ...ME, last_category_id: WORK } }),
    'GET /api/v1/categories': CATEGORIES,
    'GET /api/v1/events': { occurrences: [] },
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
  // Reset to default (week numbers on)
  storeWeekNumbers(true);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  // Restore default
  storeWeekNumbers(true);
});

const day = (iso: string) => document.querySelector<HTMLElement>(`[data-date="${iso}"]`);

async function dayViewReady() {
  await waitFor(() => expect(day('2026-10-02')).not.toBeNull());
}

describe('mobile month view: week numbers', () => {
  it('shows the ISO week-number column when enabled (default)', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();
    // Switch to month view
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());

    // The grid should have 8 columns (week column + 7 days) when weeks are shown
    const grid = document.querySelector('[role="grid"]');
    const headerRow = grid?.querySelector('[role="row"]');
    const headers = headerRow?.querySelectorAll('[role="columnheader"]');

    // Should have: Week + Mon Tue Wed Thu Fri Sat Sun = 8 columns
    expect(headers).toHaveLength(8);
    expect(headers?.[0]).toHaveAccessibleName('Week');
  });

  it('hides the week-number column when disabled', async () => {
    mockApi(baseRoutes());
    storeWeekNumbers(false);
    renderApp();
    await dayViewReady();
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());

    // The grid should have 7 columns (just the 7 days) when weeks are hidden
    const grid = document.querySelector('[role="grid"]');
    const headerRow = grid?.querySelector('[role="row"]');
    const headers = headerRow?.querySelectorAll('[role="columnheader"]');

    // Should have: Mon Tue Wed Thu Fri Sat Sun = 7 columns
    expect(headers).toHaveLength(7);
    expect(headers?.[0]).toHaveAccessibleName('Monday');
  });

  it('respects the week-numbers preference across remounts', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();

    // Initially enabled
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());
    let headers = document
      .querySelector('[role="grid"]')
      ?.querySelector('[role="row"]')
      ?.querySelectorAll('[role="columnheader"]');
    expect(headers).toHaveLength(8);

    // Disable
    storeWeekNumbers(false);
    // Remount by rendering to day view and back
    await userEvent.click(screen.getByRole('button', { name: 'Day' }));
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));

    await waitFor(() => {
      headers = document
        .querySelector('[role="grid"]')
        ?.querySelector('[role="row"]')
        ?.querySelectorAll('[role="columnheader"]');
      expect(headers).toHaveLength(7);
    });
  });

  it('shows correct week numbers in the month grid', async () => {
    mockApi(baseRoutes());
    renderApp();
    await dayViewReady();
    await userEvent.click(screen.getByRole('button', { name: 'Month' }));
    await waitFor(() => expect(day('2026-10-31')).not.toBeNull());

    // For October 2026, we expect week numbers 40-44
    const weekSpans = document.querySelectorAll('[role="rowheader"]');
    const weekNumbers = Array.from(weekSpans)
      .map((el) => el.textContent?.trim())
      .filter((text) => text && /^\d+$/.test(text))
      .map(Number);

    // Should contain week numbers for October 2026 (weeks 40-44)
    expect(weekNumbers.length).toBeGreaterThan(0);
    expect(Math.min(...weekNumbers)).toBeGreaterThanOrEqual(40);
    expect(Math.max(...weekNumbers)).toBeLessThanOrEqual(44);
  });
});
