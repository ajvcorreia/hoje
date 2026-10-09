import type { Page } from '@playwright/test';
import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop popover and grid');

test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

const TITLES = ['Alpha', 'Bravo', 'Charlie'];

/** The titles in the day cell, left to right. */
async function gridOrder(page: Page, date: string): Promise<string[]> {
  return page.evaluate((day) => {
    const cell = document.querySelector<HTMLElement>(`[data-date="${day}"]`);
    return Array.from(cell?.querySelectorAll<HTMLElement>('.cal-ev') ?? [])
      .map((el) => ({ left: el.getBoundingClientRect().left, text: el.textContent ?? '' }))
      .sort((a, b) => a.left - b.left)
      .map((e) => e.text.trim());
  }, date);
}

async function popoverOrder(page: Page, date: string): Promise<string[]> {
  const rows = page.getByRole('list', { name: `Events on ${date}` }).getByRole('listitem');
  const texts = await rows.allTextContents();
  return texts.map((t) => TITLES.find((title) => t.startsWith(title)) ?? t);
}

test('moves an event up in the day popover; the grid follows and the order persists', async ({
  page,
  account,
  api,
}) => {
  void account;
  const date = dateInCurrentMonth(12);
  await api.patchMe({ max_events_per_day: 4 });
  for (const title of TITLES) await api.createEvent(title, date);
  await page.goto('/');

  await expect.poll(() => gridOrder(page, date)).toEqual(TITLES);
  await page.locator(`[data-date="${date}"]`).click();
  const popover = page.getByRole('dialog', { name: /Events on/ });
  await expect(popover).toBeVisible();
  expect(await popoverOrder(page, date)).toEqual(TITLES);
  await expect(popover.getByText('Order is shared by all days of a multi-day event')).toBeVisible();
  await expect(popover.getByRole('button', { name: 'Move Alpha up' })).toBeDisabled();
  await expect(popover.getByRole('button', { name: 'Move Charlie down' })).toBeDisabled();

  const reorder = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/events/reorder') && r.request().method() === 'POST',
  );
  await popover.getByRole('button', { name: 'Move Charlie up' }).click();
  expect((await reorder).status()).toBe(204);

  await expect.poll(() => popoverOrder(page, date)).toEqual(['Alpha', 'Charlie', 'Bravo']);
  await expect.poll(() => gridOrder(page, date)).toEqual(['Alpha', 'Charlie', 'Bravo']);

  // Moving it again (keyboard operable): Charlie to the top.
  const second = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/events/reorder') && r.request().method() === 'POST',
  );
  await popover.getByRole('button', { name: 'Move Charlie up' }).press('Enter');
  expect((await second).status()).toBe(204);
  await expect.poll(() => gridOrder(page, date)).toEqual(['Charlie', 'Alpha', 'Bravo']);

  await page.reload();
  await expect.poll(() => gridOrder(page, date)).toEqual(['Charlie', 'Alpha', 'Bravo']);
  await page.locator(`[data-date="${date}"]`).click();
  expect(await popoverOrder(page, date)).toEqual(['Charlie', 'Alpha', 'Bravo']);
});
