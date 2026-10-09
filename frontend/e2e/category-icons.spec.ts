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
