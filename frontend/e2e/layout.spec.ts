import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

const pad = (n: number) => String(n).padStart(2, '0');

test.describe('desktop month grid', () => {
  test.beforeEach(async ({ page, account }) => {
    void account;
    await page.goto('/');
    await expect(page.locator('.cal-scroll')).toBeVisible();
  });

  test('has 12 month columns', async ({ page }) => {
    await expect(page.locator('[data-month]')).toHaveCount(12);
  });

  test('day 1 sits on the row of its weekday', async ({ page }) => {
    const year = new Date().getFullYear();
    const rows: { month: number; weekday: number; y: number }[] = [];
    for (let month = 0; month < 12; month += 1) {
      const y = await page
        .locator(`[data-date="${year}-${pad(month + 1)}-01"]`)
        .evaluate((el) => el.getBoundingClientRect().y);
      rows.push({ month, weekday: new Date(year, month, 1).getDay(), y });
    }
    let same = 0;
    let different = 0;
    for (const a of rows) {
      for (const b of rows) {
        if (b.month <= a.month) continue;
        if (a.weekday === b.weekday) {
          expect(Math.abs(a.y - b.y), `months ${a.month} and ${b.month}`).toBeLessThan(0.5);
          same += 1;
        } else {
          expect(Math.abs(a.y - b.y), `months ${a.month} and ${b.month}`).toBeGreaterThan(5);
          different += 1;
        }
      }
    }
    expect(same).toBeGreaterThan(0);
    expect(different).toBeGreaterThan(0);
  });

  test('all 37 rows fit without vertical scrolling', async ({ page }) => {
    const scroll = page.locator('.cal-scroll');
    await expect
      .poll(() => scroll.evaluate((el) => el.scrollHeight - el.clientHeight))
      .toBeLessThanOrEqual(0);

    const weekdayRows = page.locator('.cal-gutter .cal-wd');
    await expect(weekdayRows).toHaveCount(37);
    const container = await scroll.boundingBox();
    const first = await weekdayRows.first().boundingBox();
    const last = await weekdayRows.last().boundingBox();
    expect(first && last && container).toBeTruthy();
    expect(first?.y).toBeGreaterThanOrEqual(container?.y ?? 0);
    expect((last?.y ?? 0) + (last?.height ?? 0)).toBeLessThanOrEqual(
      (container?.y ?? 0) + (container?.height ?? 0) + 1,
    );
  });

  test('scrolls horizontally in a narrow window', async ({ page }) => {
    await page.setViewportSize({ width: 1000, height: 900 });
    const scroll = page.locator('.cal-scroll');
    await expect
      .poll(() => scroll.evaluate((el) => el.scrollWidth - el.clientWidth))
      .toBeGreaterThan(0);
    await scroll.evaluate((el) => {
      el.scrollLeft = el.scrollWidth;
    });
    await expect.poll(() => scroll.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
  });
});

test.describe('vertical multi-day labels', () => {
  test('rotated label spans the whole block and clicks pass through', async ({
    page,
    account,
    api,
  }) => {
    void account;
    const start = dateInCurrentMonth(10);
    const middle = dateInCurrentMonth(11);
    await api.createEvent('Conference', start, { end_date: dateInCurrentMonth(12) });

    await page.goto('/settings');
    await page.getByLabel('Multi-day event names').selectOption('vertical');

    await page.goto('/');
    const label = page.locator('.cal-vlabel');
    await expect(label).toHaveCount(1);
    await expect(label).toHaveText('Conference');
    await expect(label).toHaveCSS('writing-mode', 'vertical-rl');

    const cellBox = await page.locator(`[data-date="${start}"]`).boundingBox();
    const labelBox = await label.boundingBox();
    expect(cellBox && labelBox).toBeTruthy();
    expect(labelBox?.height).toBeGreaterThan((cellBox?.height ?? 0) * 3 - 2);
    expect(labelBox?.height).toBeLessThan((cellBox?.height ?? 0) * 3 + 2);

    await page.locator(`[data-date="${middle}"]`).click();
    await expect(page.getByRole('dialog', { name: /^Events on / })).toBeVisible();
  });
});
