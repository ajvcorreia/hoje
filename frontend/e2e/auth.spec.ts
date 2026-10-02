import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8190';

// Needs a running stack with an empty database (first-run registration open).
test.skip(!process.env.E2E_BASE_URL, 'Set E2E_BASE_URL to run against a live stack');

test('setup, log out, log in', async ({ page, isMobile }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = 'correct horse battery staple';

  await page.goto(`${BASE_URL}/`);
  await expect(page).toHaveURL(/\/setup$/);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('banner')).toContainText('Hoje');

  // Log out: header menu on desktop, Settings on mobile.
  if (isMobile) {
    await page.goto(`${BASE_URL}/settings`);
    await page.getByRole('button', { name: 'Log out' }).click();
  } else {
    await page.getByRole('button', { name: /account menu/i }).click();
    await page.getByRole('menuitem', { name: 'Log out' }).click();
  }
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('banner')).toContainText('Hoje');
  await expect(page).not.toHaveURL(/\/login/);
});
