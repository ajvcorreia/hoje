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

  test('unused rows are plain grey and each month has its own outline', async ({ page }) => {
    const year = new Date().getFullYear();
    // February always has unused rows before and after it.
    const feb = page.locator('[data-month="1"]');
    const empty = feb.locator('.cal-empty').first();
    const emptyStyle = await empty.evaluate((el) => {
      const s = getComputedStyle(el);
      return { bottom: s.borderBottomWidth, right: s.borderRightWidth };
    });
    expect(emptyStyle).toEqual({ bottom: '0px', right: '0px' });
    expect(await feb.evaluate((el) => getComputedStyle(el).borderLeftWidth)).toBe('0px');

    const outline = feb.locator('.cal-month-outline');
    const box = await outline.boundingBox();
    const first = await page.locator(`[data-date="${year}-02-01"]`).boundingBox();
    const lastDay = new Date(year, 2, 0).getDate();
    const last = await page.locator(`[data-date="${year}-02-${lastDay}"]`).boundingBox();
    const week = await feb.locator('.cal-wk').first().boundingBox();
    expect(box && first && last && week).toBeTruthy();
    if (!box || !first || !last || !week) return;
    // Spans exactly the month's days, and includes the week-number column on the left.
    expect(Math.abs(box.y - first.y)).toBeLessThan(1.5);
    expect(Math.abs(box.y + box.height - (last.y + last.height))).toBeLessThan(1.5);
    expect(box.x).toBeLessThanOrEqual(week.x + 0.5);
    expect(Math.abs(box.x + box.width - (first.x + first.width))).toBeLessThan(1.5);
    expect(await outline.evaluate((el) => getComputedStyle(el).borderTopWidth)).toBe('2px');
  });
});

/** ISO 8601 week number of a local date. */
function isoWeek(date: Date): number {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = Date.UTC(d.getUTCFullYear(), 0, 1);
  return Math.ceil(((d.getTime() - yearStart) / 86_400_000 + 1) / 7);
}

test.describe('per-event vertical labels', () => {
  test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

  test('large bold rotated label spans the whole block and clicks pass through', async ({
    page,
    account,
    api,
  }) => {
    void account;
    const start = dateInCurrentMonth(10);
    const middle = dateInCurrentMonth(11);
    await api.createEvent('Conference', start, {
      end_date: dateInCurrentMonth(12),
      label_vertical: true,
    });

    await page.goto('/');
    const label = page.locator('.cal-vlabel');
    await expect(label).toHaveCount(1);
    await expect(label).toHaveText('Conference');
    const text = label.locator('.cal-vlabel-text');
    await expect(text).toHaveCSS('writing-mode', 'vertical-rl');
    const weight = await text.evaluate((el) => Number(getComputedStyle(el).fontWeight));
    expect(weight).toBeGreaterThanOrEqual(700);
    const size = await text.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(size).toBeGreaterThanOrEqual(18);

    const cellBox = await page.locator(`[data-date="${start}"]`).boundingBox();
    const labelBox = await label.boundingBox();
    expect(cellBox && labelBox).toBeTruthy();
    expect(labelBox?.height).toBeGreaterThan((cellBox?.height ?? 0) * 3 - 2);
    expect(labelBox?.height).toBeLessThan((cellBox?.height ?? 0) * 3 + 2);

    await page.locator(`[data-date="${middle}"]`).click();
    await expect(page.getByRole('dialog', { name: /^Events on / })).toBeVisible();
  });

  test('a multi-day event without the flag keeps a horizontal title', async ({
    page,
    account,
    api,
  }) => {
    void account;
    const start = dateInCurrentMonth(10);
    await api.createEvent('Retreat', start, { end_date: dateInCurrentMonth(12) });
    await page.goto('/');
    await expect(page.locator(`[data-date="${start}"]`)).toContainText('Retreat');
    await expect(page.locator('.cal-vlabel')).toHaveCount(0);
  });
});

test.describe('week numbers, text size and day-number column', () => {
  test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

  test('week-number cells show the ISO week of the current month', async ({ page, account }) => {
    void account;
    await page.goto('/');
    const now = new Date();
    const cells = page.locator(`[data-month="${now.getMonth()}"] .cal-wk`);
    await expect(cells.first()).toBeVisible();
    await expect(cells.first()).toHaveText(
      String(isoWeek(new Date(now.getFullYear(), now.getMonth(), 1))),
    );
    const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    await expect(cells.last()).toHaveText(String(isoWeek(last)));
    // The day number lives in its own outlined sub-column.
    const num = page.locator(`[data-date="${dateInCurrentMonth(5)}"] .cal-num`);
    await expect(num).toBeVisible();
    expect(await num.evaluate((el) => getComputedStyle(el).borderRightWidth)).toBe('1px');
  });

  test('Large text size increases the root font size', async ({ page, account }) => {
    void account;
    await page.goto('/settings');
    const root = () =>
      page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
    const before = await root();
    await page.getByLabel('Text size').selectOption('large');
    await expect.poll(root).toBeGreaterThan(before);
    expect(await root()).toBeCloseTo(before * 1.125, 1);
  });

  test('default text size still fits all rows without vertical scroll', async ({
    page,
    account,
  }) => {
    void account;
    await page.goto('/');
    const scroll = page.locator('.cal-scroll');
    await expect(scroll).toBeVisible();
    await expect
      .poll(() => scroll.evaluate((el) => el.scrollHeight - el.clientHeight))
      .toBeLessThanOrEqual(0);
  });
});

test.describe('fit columns to text', () => {
  test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

  test('a long title widens its month column and is not truncated', async ({
    page,
    account,
    api,
  }) => {
    void account;
    const title = 'A very long event title that needs a lot more room than a column offers';
    expect(title.length).toBeGreaterThan(60);
    const date = dateInCurrentMonth(10);
    await api.createEvent(title, date);

    await page.goto('/settings');
    await page.getByRole('checkbox', { name: 'Fit columns to text' }).check();
    await page.goto('/');

    const now = new Date();
    const month = now.getMonth();
    const other = (month + 6) % 12;
    const width = (m: number) =>
      page.locator(`[data-month="${m}"]`).evaluate((el) => el.getBoundingClientRect().width);
    await expect(page.locator(`[data-date="${date}"] .cal-ev`)).toHaveText(title);
    await expect.poll(() => width(month)).toBeGreaterThan((await width(other)) + 100);

    const ev = page.locator(`[data-date="${date}"] .cal-ev`);
    await expect
      .poll(() => ev.evaluate((el) => el.scrollWidth - el.clientWidth))
      .toBeLessThanOrEqual(0);

    const scroll = page.locator('.cal-scroll');
    await expect
      .poll(() => scroll.evaluate((el) => el.scrollHeight - el.clientHeight))
      .toBeLessThanOrEqual(0);
  });
});
