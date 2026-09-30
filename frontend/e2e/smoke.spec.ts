import { test, expect } from '@playwright/test';

// Placeholder: real end-to-end specs arrive with the feature phases.
test.skip('shell renders with navigation', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('banner')).toContainText('Hoje');
});
