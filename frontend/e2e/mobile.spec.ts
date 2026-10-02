import { expect, test, todayIso } from './fixtures';

test.skip(({ isMobile }) => !isMobile, 'phone layout only');

test.beforeEach(async ({ page, account }) => {
  void account;
  await page.goto('/');
  await expect(page.getByRole('list', { name: 'Week' })).toBeVisible();
});

test('bottom navigation offers Calendar and Settings', async ({ page }) => {
  const nav = page.getByRole('navigation', { name: 'Main (mobile)' });
  await expect(nav.getByRole('link', { name: 'Calendar' })).toBeVisible();
  await expect(nav.getByRole('link', { name: 'Settings' })).toBeVisible();
});

test('shows the day view with a week strip and no desktop grid', async ({ page }) => {
  await expect(page.getByRole('list', { name: 'Week' }).getByRole('button')).toHaveCount(7);
  await expect(page.locator('.cal-scroll')).toHaveCount(0);
  await expect(page.locator('[data-month]')).toHaveCount(0);
});

test('does not scroll horizontally at 360 px', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
});

test('quick add creates a card; month view shows a dot', async ({ page }) => {
  const title = `Mobile ${Date.now()}`;
  await page.getByRole('button', { name: 'Add event' }).click();
  const sheet = page.getByRole('dialog', { name: /^Add event/ });
  const field = sheet.getByLabel('Add an event');
  await field.fill(title);
  await field.press('Enter');

  const list = page.getByRole('list', { name: `Events on ${todayIso()}` });
  await expect(list.getByRole('button', { name: new RegExp(title) })).toBeVisible();

  await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' }).click();
  const cell = page.getByRole('grid').locator(`[data-date="${todayIso()}"]`);
  await expect(cell.locator('.m-dot')).toHaveCount(1);
});
