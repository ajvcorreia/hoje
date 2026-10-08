import { dateInCurrentMonth, expect, test } from './fixtures';

// A rotated name that does not fit its block on one line wraps at word boundaries into up to
// three lines (side by side, each bottom-to-top) and the lane column grows with them.
test.skip(({ isMobile }) => isMobile, 'desktop grid only');

// Tall enough that a 3-day block has room for a long word at a readable size.
test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 1200 }));

const d = dateInCurrentMonth;

interface Measured {
  lines: number;
  size: number;
  /** Every line's text fits its own box (no scroll overflow along the line). */
  clipped: string[];
  /** The painted text lies inside the label box. */
  outside: boolean;
  labelWidth: number;
  labelHeight: number;
  text: string;
}

for (const name of ['Quarterly stakeholder alignment', 'Team offsite planning day']) {
  test(`"${name}" wraps in a 3-day block, nothing clipped, lane grows`, async ({
    page,
    account,
    api,
  }) => {
    void account;
    await api.createEvent(name, d(10), { end_date: d(12), label_vertical: true });
    await page.goto('/');

    const label = page.locator('.cal-vlabel', { hasText: name });
    await expect(label).toHaveCount(1);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(200);

    const m = await label.evaluate((el): Measured => {
      const text = el.querySelector<HTMLElement>('.cal-vlabel-text') as HTMLElement;
      const lines = Array.from(text.querySelectorAll<HTMLElement>('.cal-vline'));
      const clipped = lines
        .filter((l) => l.scrollHeight > l.clientHeight + 1 || l.scrollWidth > l.clientWidth + 1)
        .map((l) => l.textContent ?? '');
      if (text.scrollHeight > text.clientHeight + 1) clipped.push('(text)');
      const range = document.createRange();
      range.selectNodeContents(text);
      const t = range.getBoundingClientRect();
      const h = el.getBoundingClientRect();
      return {
        lines: lines.length,
        size: parseFloat(getComputedStyle(text).fontSize),
        clipped,
        outside:
          t.left < h.left - 1 ||
          t.right > h.right + 1 ||
          t.top < h.top - 1 ||
          t.bottom > h.bottom + 1,
        labelWidth: h.width,
        labelHeight: h.height,
        text: text.textContent ?? '',
      };
    });

    expect(m.text).toBe(name);
    expect(m.lines).toBeGreaterThanOrEqual(2);
    expect(m.lines).toBeLessThanOrEqual(3);
    expect(m.clipped).toEqual([]);
    expect(m.outside).toBe(false);
    expect(m.size).toBeGreaterThanOrEqual(8.99);
    expect(m.labelWidth).toBeGreaterThan(17);
    expect(Math.abs(m.labelWidth - (Math.ceil(1.15 * m.size * m.lines) + 2))).toBeLessThanOrEqual(
      1,
    );

    // The label never grows past the preferred size: wrapping or shrinking only makes it smaller.
    expect(m.size).toBeLessThanOrEqual(12.01);

    // Clicks pass through the label to the day cell under it.
    const box = await label.boundingBox();
    expect(box).toBeTruthy();
    await page.mouse.click(
      (box?.x ?? 0) + (box?.width ?? 0) / 2,
      (box?.y ?? 0) + (box?.height ?? 0) / 2,
    );
    await expect(page.getByRole('dialog', { name: /^Events on / })).toBeVisible();
  });
}

test('an 8-day block with a short name stays one line in the 16px lane', async ({
  page,
  account,
  api,
}) => {
  void account;
  await api.createEvent('Conference', d(10), { end_date: d(17), label_vertical: true });
  await page.goto('/');

  const label = page.locator('.cal-vlabel', { hasText: 'Conference' });
  await expect(label).toHaveCount(1);
  await expect(label.locator('.cal-vline')).toHaveCount(1);
  const box = await label.boundingBox();
  expect(Math.abs((box?.width ?? 0) - 16)).toBeLessThanOrEqual(1);
  const size = await label
    .locator('.cal-vlabel-text')
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(size).toBeGreaterThanOrEqual(11.99);
});

test('lanes are sized per label: a wrapped label widens only its own lane', async ({
  page,
  account,
  api,
}) => {
  void account;
  await api.patchMe({ max_events_per_day: 4 });
  await api.createEvent('Quarterly stakeholder alignment', d(10), {
    end_date: d(12),
    label_vertical: true,
  });
  await api.createEvent('Doha', d(10), { end_date: d(17), label_vertical: true });
  await page.goto('/');

  const wide = page.locator('.cal-vlabel', { hasText: 'Quarterly' });
  const narrow = page.locator('.cal-vlabel', { hasText: 'Doha' });
  await expect(wide).toHaveCount(1);
  await expect(narrow).toHaveCount(1);
  const w = await wide.boundingBox();
  const n = await narrow.boundingBox();
  expect(w?.width).toBeGreaterThan(17);
  expect(Math.abs((n?.width ?? 0) - 16)).toBeLessThanOrEqual(1);
  // Side by side (the longer block takes the first lane): the second lane starts where the first ends.
  expect(Math.abs((w?.x ?? 0) - ((n?.x ?? 0) + (n?.width ?? 0)))).toBeLessThanOrEqual(2);
});
