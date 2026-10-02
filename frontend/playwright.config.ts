import { defineConfig, devices } from '@playwright/test';

// The suite expects a throwaway stack with registration open (deploy/compose.e2e.yml,
// started by deploy/e2e.sh). Every spec registers its own users, so the database never
// needs to be empty.
export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8192',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop-chromium',
      testIgnore: /mobile\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'mobile',
      testMatch: /(auth|mobile)\.spec\.ts/,
      use: { ...devices['Pixel 7'] },
    },
  ],
});
