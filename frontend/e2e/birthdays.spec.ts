import { dateInCurrentMonth, expect, test } from './fixtures';

// deploy/compose.e2e.yml runs a fake FelizAnniv (deploy/e2e/fake_felizanniv.py) at this fixed
// address, allowed for the API and the worker with HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS.
const FAKE_URL = 'http://10.231.77.10:4000';
const FAKE_KEY = 'fa_live_e2e_fake_key_0123456789';
const ADA = "Ada Lovelace's birthday";

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test('connects to FelizAnniv, syncs and shows the birthdays as ordinary events', async ({
  page,
  api,
}) => {
  void api; // registers and signs in the user
  await page.goto('/settings');
  const section = page.getByRole('region', { name: 'FelizAnniv birthdays' });
  const address = section.getByLabel('FelizAnniv address');
  const key = section.getByLabel('API key');
  const save = section.getByRole('button', { name: 'Save & test' });

  // The SSRF guard refuses the server's own loopback before any request is made.
  await address.fill('http://127.0.0.1:8000');
  await key.fill(FAKE_KEY);
  await save.click();
  await expect(section.getByRole('alert')).toContainText('That address is not allowed');

  // A wrong key is caught by the connection test and nothing is saved.
  await address.fill(FAKE_URL);
  await key.fill('fa_live_not_the_right_key');
  await save.click();
  await expect(section.getByRole('alert')).toContainText('FelizAnniv rejected the API key');
  await expect(section.getByRole('button', { name: 'Sync now' })).toHaveCount(0);

  await key.fill(FAKE_KEY);
  await save.click();
  await expect(section.getByText(FAKE_URL, { exact: true })).toBeVisible();
  await expect(section.getByText('fa_live_e2…')).toBeVisible();
  await expect(key).toHaveValue('');
  // The worker (2 s interval in the e2e stack) runs the full sync.
  await expect(section.getByText(/Last synced .* · 2 birthdays/)).toBeVisible({ timeout: 20_000 });

  // The birthday is an ordinary event in a "Birthdays" category, with its own chip.
  await page.goto('/');
  const cell = page.locator(`[data-date="${dateInCurrentMonth(15)}"]`);
  await expect(cell.locator('.cal-ev')).toHaveText(ADA);
  await expect(page.getByRole('button', { name: /^Birthdays/ })).toBeVisible();

  // It opens in the normal editor and says it is kept in sync.
  await cell.click();
  await page
    .getByRole('dialog', { name: /^Events on / })
    .getByRole('button', { name: ADA })
    .click();
  const editor = page.getByRole('dialog', { name: 'Edit event' });
  await expect(editor.getByLabel('Title')).toHaveValue(ADA);
  await expect(editor.getByText(/Synced with FelizAnniv/)).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(editor).toBeHidden();

  // Disconnecting keeps the events, which are then plain events.
  await page.goto('/settings');
  await section.getByRole('button', { name: 'Disconnect' }).click();
  const dialog = page.getByRole('dialog', { name: 'Disconnect FelizAnniv?' });
  await expect(dialog).toContainText('stay in your calendar');
  await dialog.getByRole('button', { name: 'Disconnect' }).click();
  await expect(section.getByRole('button', { name: 'Sync now' })).toHaveCount(0);
  await page.goto('/');
  await expect(cell.locator('.cal-ev')).toHaveText(ADA);
  await cell.click();
  await page
    .getByRole('dialog', { name: /^Events on / })
    .getByRole('button', { name: ADA })
    .click();
  await expect(page.getByRole('dialog', { name: 'Edit event' }).getByLabel('Title')).toHaveValue(
    ADA,
  );
  await expect(page.getByText(/Synced with FelizAnniv/)).toHaveCount(0);
});
