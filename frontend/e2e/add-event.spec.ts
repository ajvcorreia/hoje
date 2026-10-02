import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test('add an event from the day popover, open it, delete and undo', async ({ page, api }) => {
  const date = dateInCurrentMonth(15);
  const title = `Dentist ${Date.now()}`;

  await page.goto('/settings');
  await page
    .getByRole('navigation', { name: 'Main', exact: true })
    .getByRole('link', { name: 'Calendar' })
    .click();
  await expect(page.locator('.cal-scroll')).toBeVisible();

  const cell = page.locator(`[data-date="${date}"]`);
  await cell.click();
  const popover = page.getByRole('dialog', { name: /^Events on / });
  const field = popover.getByLabel('Add an event');
  await expect(field).toBeFocused();
  await field.fill(title);
  await field.press('Enter');

  await expect(popover).toBeHidden();
  await expect(cell.locator('.cal-ev')).toHaveText(title);

  // The editor shows the title and the category the server picked.
  await cell.click();
  await page
    .getByRole('dialog', { name: /^Events on / })
    .getByRole('button', { name: title })
    .click();
  const editor = page.getByRole('dialog', { name: 'Edit event' });
  await expect(editor.getByLabel('Title')).toHaveValue(title);

  const [stored] = await api.events(date, date);
  const categories = await api.categories();
  const category = categories.find((c) => c.id === stored?.category_id);
  expect(category).toBeDefined();
  await expect(editor.getByLabel('Category')).toHaveValue(category?.id ?? '');
  await expect(editor.locator('#event-category option:checked')).toHaveText(category?.name ?? '');

  // Delete, then undo from the toast.
  await editor.getByRole('button', { name: 'Delete' }).click();
  await expect(editor).toBeHidden();
  await expect(cell.locator('.cal-ev')).toHaveCount(0);
  const toast = page.getByRole('status');
  await expect(toast).toContainText('Event deleted');
  await toast.getByRole('button', { name: 'Undo' }).click();
  await expect(cell.locator('.cal-ev')).toHaveText(title);
  await expect.poll(async () => (await api.events(date, date)).length).toBe(1);
});
