import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

const d = dateInCurrentMonth;
const fit = (el: Element) => ({
  size: parseFloat(getComputedStyle(el).fontSize),
  // Vertical text: the name runs along the element's height.
  overflow: el.scrollHeight - el.clientHeight,
});

test('a vertical label is drawn at the preferred size and its lane widens with it', async ({
  page,
  account,
  api,
}) => {
  void account;
  await api.patchMe({ vertical_text_size: 24 });
  await api.createEvent('Hi', d(10), { end_date: d(17), label_vertical: true });
  await page.goto('/');

  const label = page.locator('.cal-vlabel', { hasText: 'Hi' });
  await expect(label).toHaveCount(1);
  const { size, overflow } = await label.locator('.cal-vlabel-text').evaluate(fit);
  expect(size).toBeGreaterThan(23.5);
  expect(size).toBeLessThan(24.5);
  expect(overflow).toBeLessThanOrEqual(1);
  const box = await label.boundingBox();
  expect(box?.width).toBeGreaterThan(Math.ceil(1.15 * 24) + 2 - 1);
  expect(box?.width).toBeLessThan(Math.ceil(1.15 * 24) + 2 + 1);
});

test('the label shrinks only when its name does not fit the block height', async ({
  page,
  account,
  api,
}) => {
  void account;
  await api.patchMe({ vertical_text_size: 24 });
  await api.createEvent('Erbil trip', d(3), { end_date: d(5), label_vertical: true });
  await page.goto('/');

  const text = page.locator('.cal-vlabel', { hasText: 'Erbil trip' }).locator('.cal-vlabel-text');
  await expect(text).toBeVisible();
  const { size, overflow } = await text.evaluate(fit);
  expect(size).toBeLessThan(24);
  expect(size).toBeGreaterThanOrEqual(9);
  expect(overflow).toBeLessThanOrEqual(1);
});

test('a name that cannot fit even when shrunk stays a horizontal title', async ({
  page,
  account,
  api,
}) => {
  void account;
  await api.patchMe({ vertical_text_size: 32 });
  await api.createEvent('Lisbon conference dinner', d(10), {
    end_date: d(11),
    label_vertical: true,
  });
  await page.goto('/');

  await expect(
    page.locator('.cal-ev', { hasText: 'Lisbon conference dinner' }).first(),
  ).toBeVisible();
  await expect(page.locator('.cal-vlabel')).toHaveCount(0);
});
