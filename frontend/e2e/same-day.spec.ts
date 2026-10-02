import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

const TOLERANCE = 3;

test('one event fills the whole cell', async ({ page, api }) => {
  const date = dateInCurrentMonth(10);
  await api.createEvent('Solo', date);
  await page.goto('/');

  const cell = page.locator(`[data-date="${date}"]`);
  const events = cell.locator('.cal-ev');
  await expect(events).toHaveCount(1);
  await expect(events).toHaveAttribute('data-lane', 'full');
  const cellBox = await cell.boundingBox();
  const eventBox = await events.boundingBox();
  expect(eventBox?.width).toBeGreaterThan((cellBox?.width ?? 0) - TOLERANCE);
});

test('two events render as two halves side by side', async ({ page, api }) => {
  const date = dateInCurrentMonth(11);
  await api.createEvent('Alpha', date);
  await api.createEvent('Bravo', date);
  await page.goto('/');

  const cell = page.locator(`[data-date="${date}"]`);
  const events = cell.locator('.cal-ev');
  await expect(events).toHaveCount(2);
  const cellBox = await cell.boundingBox();
  const left = await events.nth(0).boundingBox();
  const right = await events.nth(1).boundingBox();
  expect(cellBox && left && right).toBeTruthy();
  expect(Math.abs((left?.y ?? 0) - (right?.y ?? 99))).toBeLessThan(1);
  expect(right?.x).toBeGreaterThan((left?.x ?? 0) + 10);
  for (const box of [left, right]) {
    expect(Math.abs((box?.width ?? 0) - (cellBox?.width ?? 0) / 2)).toBeLessThan(TOLERANCE);
  }
  await expect(events.nth(0)).toHaveText('Alpha');
  await expect(events.nth(1)).toHaveText('Bravo');
});

test('three events show two halves and a +1 chip; the popover lists all three', async ({
  page,
  api,
}) => {
  const date = dateInCurrentMonth(12);
  for (const title of ['Alpha', 'Bravo', 'Charlie']) await api.createEvent(title, date);
  await page.goto('/');

  const cell = page.locator(`[data-date="${date}"]`);
  await expect(cell.locator('.cal-ev')).toHaveCount(2);
  await expect(cell.locator('.cal-more')).toHaveText('+1');

  await cell.click();
  const popover = page.getByRole('dialog', { name: /^Events on / });
  const list = popover.getByRole('list', { name: `Events on ${date}` });
  await expect(list.getByRole('listitem')).toHaveCount(3);
  for (const title of ['Alpha', 'Bravo', 'Charlie']) {
    await expect(list.getByRole('button', { name: new RegExp(title) })).toBeVisible();
  }
});
