import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

/** Horizontal centre gap between the current month column and the scroll viewport. */
async function centreGap(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const scroll = document.querySelector('.cal-scroll') as HTMLElement;
    const month = document.querySelector('[data-current]')?.closest('[data-month]') as HTMLElement;
    const s = scroll.getBoundingClientRect();
    const c = month.getBoundingClientRect();
    const max = scroll.scrollWidth - scroll.clientWidth;
    return {
      gap: c.left + c.width / 2 - (s.left + s.width / 2),
      atEdge: scroll.scrollLeft <= 1 || scroll.scrollLeft >= max - 1,
      scrollLeft: scroll.scrollLeft,
    };
  });
}

test('the current month is centred on load', async ({ page, account }) => {
  void account;
  await page.goto('/');
  await expect(page.locator('.cal-cell[data-today]')).toHaveCount(1);
  await page.evaluate(() => document.fonts.ready);
  await expect
    .poll(async () => {
      const r = await centreGap(page);
      return r.atEdge || Math.abs(r.gap) <= 3;
    })
    .toBe(true);
});

test('hovering a row highlights its weekday label and tints the row in every month', async ({
  page,
  account,
  api,
}) => {
  void account;
  const date = dateInCurrentMonth(15);
  await api.createEvent('Hover target', date);
  await page.goto('/');
  const cell = page.locator(`.cal-cell[data-date="${date}"]`);
  await expect(cell).toBeVisible();
  const row = await cell.getAttribute('data-row');
  const label = page.locator(`.cal-wd[data-row="${row}"]`);
  const other = page.locator(`.cal-wd[data-row="${(Number(row) + 1) % 7}"]`);
  const sibling = page.locator(`.cal-cell[data-row="${row}"], .cal-empty[data-row="${row}"]`);
  const bg = (l: import('@playwright/test').Locator) =>
    l.first().evaluate((el) => getComputedStyle(el).backgroundColor);
  const img = (l: import('@playwright/test').Locator) =>
    l.last().evaluate((el) => getComputedStyle(el).backgroundImage);

  const before = await bg(label);
  const imgBefore = await img(sibling);
  await cell.hover();
  await expect(page.locator('.cal-grid')).toHaveAttribute('data-hover-row', row ?? '');
  expect(await bg(label)).not.toBe(before);
  expect(await bg(label)).not.toBe(await bg(other));
  expect(await label.first().evaluate((el) => getComputedStyle(el).fontWeight)).toBe('700');
  expect(await img(sibling)).not.toBe(imgBefore);

  await page.mouse.move(2, 2);
  await expect(page.locator('.cal-grid')).not.toHaveAttribute('data-hover-row');
  expect(await bg(label)).toBe(before);
});

test('a late re-measure does not re-centre once the user has scrolled', async ({
  page,
  account,
}) => {
  void account;
  await page.goto('/');
  await expect(page.locator('.cal-cell[data-today]')).toHaveCount(1);
  const scroll = page.locator('.cal-scroll');
  const max = await scroll.evaluate((el) => el.scrollWidth - el.clientWidth);
  test.skip(max < 50, 'nothing to scroll at this width');
  await scroll.hover();
  await page.mouse.wheel(0, 0);
  await page.mouse.wheel(-40, 0);
  await scroll.evaluate((el) => {
    el.scrollLeft = 0;
  });
  await page.evaluate(() => window.dispatchEvent(new Event('resize')));
  await page.waitForTimeout(300);
  expect(await scroll.evaluate((el) => el.scrollLeft)).toBeLessThanOrEqual(1);
});
