import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

/** WCAG contrast of two `rgb()/rgba()` strings, evaluated in the page. */
function contrastOf(fg: string, bg: string): number {
  const parse = (c: string) => {
    const m = /rgba?\(([^)]+)\)/.exec(c);
    const [r = 0, g = 0, b = 0] = (m?.[1] ?? '').split(/[ ,/]+/).map(Number);
    return [r, g, b];
  };
  const lum = (c: string) => {
    const [r = 0, g = 0, b = 0] = parse(c).map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [a, b] = [lum(fg), lum(bg)];
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

test('the high-contrast light theme is selectable and every sampled pair reaches AAA', async ({
  page,
  account,
  api,
}) => {
  void account;
  const [work] = await api.categories();
  expect(work).toBeDefined();
  await api.createEvent('Contrast check', dateInCurrentMonth(12), {
    category_id: work?.id,
  });

  await page.goto('/settings');
  await page.getByLabel('Theme').selectOption({ label: 'Light (high contrast)' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light-contrast');
  await expect
    .poll(() => page.evaluate(() => getComputedStyle(document.documentElement).colorScheme))
    .toBe('light');

  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light-contrast');
  const event = page.locator('.cal-ev', { hasText: 'Contrast check' }).first();
  await expect(event).toBeVisible();

  const samples = await page.evaluate(() => {
    const colours = (el: Element | null) => {
      if (!el) return null;
      const cs = getComputedStyle(el);
      return { fg: cs.color, bg: cs.backgroundColor };
    };
    return {
      body: colours(document.body),
      event: colours(document.querySelector('.cal-ev')),
      todayCell: colours(document.querySelector('[data-today]')),
    };
  });
  expect(samples.body).not.toBeNull();
  expect(contrastOf(samples.body?.fg ?? '', samples.body?.bg ?? '')).toBeGreaterThanOrEqual(7);
  expect(contrastOf(samples.event?.fg ?? '', samples.event?.bg ?? '')).toBeGreaterThanOrEqual(7);
  expect(samples.todayCell).not.toBeNull();
  expect(
    contrastOf(samples.todayCell?.fg ?? '', samples.todayCell?.bg ?? ''),
  ).toBeGreaterThanOrEqual(7);

  // The choice survives a reload.
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light-contrast');
});

test('a category with a new colour renders in the grid with its data-cat', async ({
  page,
  account,
  api,
}) => {
  void account;
  const res = await api.post('/api/v1/categories', { name: 'Fuchsia things', colour: 'fuchsia' });
  expect(res.status(), await res.text()).toBe(201);
  const created = (await res.json()) as { id: string };
  await api.createEvent('Fuchsia event', dateInCurrentMonth(8), { category_id: created.id });

  await page.goto('/');
  const ev = page.locator('.cal-ev', { hasText: 'Fuchsia event' }).first();
  await expect(ev).toBeVisible();
  await expect(ev).toHaveAttribute('data-cat', 'fuchsia');
});
