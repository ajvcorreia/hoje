import type { Locator, Page } from '@playwright/test';
import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

interface Box {
  x: number;
  width: number;
}

async function box(locator: Locator): Promise<Box> {
  await expect(locator).toHaveCount(1);
  const b = await locator.boundingBox();
  expect(b).toBeTruthy();
  return b as Box;
}

const right = (b: Box) => b.x + b.width;

/**
 * Every cell with events: its coloured boxes (events, rotated columns, holiday text, "+N" chip)
 * must follow each other from the day number to the right edge, without a gap.
 */
async function gaps(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const cell of Array.from(document.querySelectorAll<HTMLElement>('.cal-cell'))) {
      const boxes = Array.from(cell.querySelectorAll<HTMLElement>('.cal-ev, .cal-hol, .cal-more'))
        .map((el) => el.getBoundingClientRect())
        .sort((a, b) => a.left - b.left);
      if (boxes.length === 0) continue;
      const c = cell.getBoundingClientRect();
      const num = (cell.querySelector('.cal-num') as HTMLElement).getBoundingClientRect();
      let edge = num.right;
      for (const b of boxes) {
        if (b.left - edge > 2)
          out.push(`${cell.dataset.date}: gap of ${b.left - edge}px at ${edge}`);
        edge = Math.max(edge, b.right);
      }
      // A rotated block alone in a cell stays one narrow column: white to its right is by design.
      const onlyRotated = !cell.querySelector('.cal-ev:not([data-rot]), .cal-hol, .cal-more');
      if (c.right - edge > 2 && !onlyRotated)
        out.push(`${cell.dataset.date}: white ${c.right - edge}px on the right`);
    }
    return out;
  });
}

test('events pack left next to a narrow rotated label and fill the cell to the right', async ({
  page,
  account,
  api,
}) => {
  void account;
  const d = dateInCurrentMonth;
  await api.createEvent('Renew unemployment Insurance', d(9));
  await api.createEvent('Doha', d(10), { end_date: d(16), label_vertical: true });
  await api.createEvent('Flight to Doha', d(10));
  await api.createEvent('Riverside Payment', d(15));
  for (const title of ['Alpha', 'Bravo', 'Charlie']) await api.createEvent(title, d(20));
  await page.goto('/');

  const label = page.locator('.cal-vlabel', { hasText: 'Doha' });
  await expect(label).toHaveCount(1);
  const num10 = await box(page.locator(`[data-date="${d(10)}"] .cal-num`));
  const doha = await box(label);

  // (a) the label is one narrow column, hard against the day number.
  expect(doha.width).toBeLessThanOrEqual(17);
  expect(Math.abs(doha.x - right(num10))).toBeLessThanOrEqual(6);

  // (b) the events of the block's days start where the label ends and fill to the cell's edge.
  for (const [day, title] of [
    [10, 'Flight to Doha'],
    [15, 'Riverside Payment'],
  ] as const) {
    const cell = page.locator(`[data-date="${d(day)}"]`);
    const cellBox = await box(cell);
    const ev = await box(cell.locator('.cal-ev', { hasText: title }));
    expect(Math.abs(ev.x - right(doha))).toBeLessThanOrEqual(4);
    expect(Math.abs(right(ev) - right(cellBox))).toBeLessThanOrEqual(3);
  }

  // (c) a day without the block: the first event starts right after the day number.
  const cell9 = page.locator(`[data-date="${d(9)}"]`);
  const num9 = await box(cell9.locator('.cal-num'));
  const first = await box(cell9.locator('.cal-ev').first());
  expect(Math.abs(first.x - right(num9))).toBeLessThanOrEqual(2);

  // (d) nothing but the right edge is white in any cell with events.
  expect(await gaps(page)).toEqual([]);
});

test('with 4 to 6 events a day, events stay contiguous from the day number to the right edge', async ({
  page,
  account,
  api,
}) => {
  void account;
  await api.patchMe({ max_events_per_day: 6 });
  const d = dateInCurrentMonth;
  for (const title of ['One', 'Two', 'Three', 'Four']) await api.createEvent(title, d(4));
  for (const title of ['Uno', 'Dos', 'Tres', 'Cuatro', 'Cinco', 'Seis']) {
    await api.createEvent(title, d(5));
  }
  await api.createEvent('Retreat', d(7), { end_date: d(11) });
  await api.createEvent('Summit', d(8), { end_date: d(14), label_vertical: true });
  await api.createEvent('Workshop', d(10), { end_date: d(13), label_vertical: true });
  for (const title of ['Breakfast', 'Lunch', 'Dinner']) await api.createEvent(title, d(9));
  await api.createEvent('Standup', d(12));
  await page.goto('/');

  await expect(page.locator('.cal-vlabel')).toHaveCount(2);
  await expect(page.locator(`[data-date="${d(5)}"] .cal-ev`)).toHaveCount(6);
  expect(await gaps(page)).toEqual([]);

  // Two overlapping rotated blocks: two narrow columns side by side, 30px at most each.
  const summit = await box(page.locator('.cal-vlabel', { hasText: 'Summit' }));
  const workshop = await box(page.locator('.cal-vlabel', { hasText: 'Workshop' }));
  expect(summit.width).toBeLessThanOrEqual(17);
  expect(workshop.width).toBeLessThanOrEqual(17);
  expect(Math.abs(workshop.x - right(summit))).toBeLessThanOrEqual(2);
});
