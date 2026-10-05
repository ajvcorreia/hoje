import { dateInCurrentMonth, expect, test } from './fixtures';

// deploy/compose.e2e.yml runs a fake FelizAnniv (deploy/e2e/fake_felizanniv.py) at this fixed
// address, allowed for the API and the worker with HOJE_INTEGRATION_ALLOWED_PRIVATE_CIDRS.
const FAKE_URL = 'http://10.231.77.10:4000';
const FAKE_KEY = 'fa_live_e2e_fake_key_0123456789';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test('connects to FelizAnniv, syncs and draws the birthdays in the calendar', async ({
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

  await page.goto('/');
  const ada = page.locator(`[data-date="${dateInCurrentMonth(15)}"] .cal-hol`);
  await expect(ada).toHaveText('\u{1F382} Ada Lovelace (30)'); // born 30 years ago

  await page.getByRole('button', { name: 'Birthdays' }).click();
  await expect(ada).toHaveCount(0);
  await page.getByRole('button', { name: 'Birthdays' }).click();
  await expect(ada).toBeVisible();

  // Disconnecting removes the synced birthdays.
  await page.goto('/settings');
  await section.getByRole('button', { name: 'Disconnect' }).click();
  const dialog = page.getByRole('dialog', { name: 'Disconnect FelizAnniv?' });
  await dialog.getByRole('button', { name: 'Disconnect' }).click();
  await expect(section.getByRole('button', { name: 'Sync now' })).toHaveCount(0);
  await page.goto('/');
  await expect(page.locator(`[data-date="${dateInCurrentMonth(15)}"]`)).toBeVisible();
  await expect(page.locator('.cal-hol[data-birthday]')).toHaveCount(0);
});
