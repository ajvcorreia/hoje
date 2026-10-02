import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test('changes made in one browser appear in another without a reload', async ({
  page,
  browser,
  baseURL,
  account,
}) => {
  const base = baseURL ?? '';
  const date = dateInCurrentMonth(17);
  const title = `Live ${Date.now()}`;

  // Context B: same user, own session.
  const contextB = await browser.newContext({
    baseURL: base,
    viewport: { width: 1440, height: 900 },
  });
  try {
    const login = await contextB.request.post('/api/v1/auth/login', {
      headers: { Origin: new URL(base).origin },
      data: { email: account.email, password: account.password },
    });
    expect(login.ok(), await login.text()).toBeTruthy();
    const pageB = await contextB.newPage();

    await page.goto('/');
    await pageB.goto('/');
    const cellA = page.locator(`[data-date="${date}"]`);
    const cellB = pageB.locator(`[data-date="${date}"]`);
    await expect(cellA).toBeVisible();
    await expect(cellB).toBeVisible();
    // Let both streams connect before anything changes.
    await pageB.waitForTimeout(1000);

    // A creates an event through the UI.
    await cellA.click();
    const popover = page.getByRole('dialog', { name: /^Events on / });
    const field = popover.getByLabel('Add an event');
    await field.fill(title);
    await field.press('Enter');
    await expect(cellA.locator('.cal-ev')).toHaveText(title);

    // B sees it within 3 s, without reloading, and is told something changed elsewhere.
    await expect(cellB.locator('.cal-ev')).toHaveText(title, { timeout: 3000 });
    await expect(pageB.getByText('Updated', { exact: true })).toBeVisible();
    await expect(page.getByText('Updated', { exact: true })).toBeHidden();

    // B deletes it; A drops it within 3 s.
    await cellB.click();
    await pageB
      .getByRole('dialog', { name: /^Events on / })
      .getByRole('button', { name: title })
      .click();
    const editor = pageB.getByRole('dialog', { name: 'Edit event' });
    await editor.getByRole('button', { name: 'Delete' }).click();
    await expect(editor).toBeHidden();
    await expect(cellA.locator('.cal-ev')).toHaveCount(0, { timeout: 3000 });
  } finally {
    await contextB.close();
  }
});
