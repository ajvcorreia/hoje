import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test('category glyphs prefix the event titles until switched off in settings', async ({
  page,
  api,
}) => {
  const date = dateInCurrentMonth(12);
  await api.createEvent('Glyph check', date);
  await api.patchMe({ show_category_icons: true });
  await page.goto('/');

  const event = page.locator(`[data-date="${date}"] .cal-ev`);
  await expect(event).toHaveText('📅 Glyph check');

  await api.patchMe({ show_category_icons: false });
  await page.reload();
  await expect(event).toHaveText('Glyph check');
});

test('icons can be kept off the calendar or off vertical labels', async ({ page, api }) => {
  const day = dateInCurrentMonth(14);
  await api.createEvent('Single day', day);
  await api.patchMe({ show_category_icons: true, icons_in_calendar: false });
  await page.goto('/');

  // Pills keep the glyph, the grid does not.
  await expect(page.getByRole('group', { name: 'Show categories' })).toContainText('📅');
  await expect(page.locator(`[data-date="${day}"] .cal-ev`)).toHaveText('Single day');

  await api.patchMe({ icons_in_calendar: true, icons_on_vertical: false });
  await page.reload();
  await expect(page.locator(`[data-date="${day}"] .cal-ev`)).toHaveText('📅 Single day');
});
