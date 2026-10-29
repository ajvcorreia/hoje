import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test.beforeEach(({ page }) => page.setViewportSize({ width: 1440, height: 900 }));

// Vertical names and joined boxes are drawn over the day cells, so the past-day mark must be
// drawn above them for vertical events to be faded or striped like the others.
test('a past joined vertical event takes the past-day mark, also on hover', async ({
  page,
  account,
  api,
}) => {
  void account;
  test.skip(new Date().getDate() < 5, 'needs three past days this month');
  await api.createEvent('Trip', dateInCurrentMonth(1), {
    end_date: dateInCurrentMonth(3),
    label_vertical: true,
  });
  await api.patchMe({ join_vertical_events: true, strike_past: false });
  await page.goto('/');
  const label = page.locator('.cal-vlabel', { hasText: 'Trip' });
  await expect(label).toHaveCount(1);
  await page.mouse.move(0, 0);
  const plain = await label.screenshot();

  await api.patchMe({ strike_past: true, past_style: 'fade', past_strength: 'strong' });
  await page.reload();
  await expect(label).toHaveAttribute('data-past');
  await page.mouse.move(0, 0);
  // The box's own fill covers the cells, so it only changes if the mark is drawn above it.
  expect((await label.screenshot()).equals(plain)).toBe(false);

  // Hovering one of its days keeps the mark over the box.
  const box = await label.boundingBox();
  if (!box) throw new Error('no label box');
  await page.mouse.move(box.x + box.width + 40, box.y + box.height / 2);
  expect((await label.screenshot()).equals(plain)).toBe(false);
});
