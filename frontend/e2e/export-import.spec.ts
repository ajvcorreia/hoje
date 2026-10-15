import { readFile } from 'node:fs/promises';
import { dateInCurrentMonth, expect, registerUser, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

test('exports one account and merges the file into another', async ({
  page,
  browser,
  baseURL,
  api,
}) => {
  const base = baseURL ?? '';
  const stamp = Date.now();
  const planned = [
    { title: `Dentist ${stamp}`, date: dateInCurrentMonth(12) },
    { title: `Flight ${stamp}`, date: dateInCurrentMonth(14) },
    { title: `Review ${stamp}`, date: dateInCurrentMonth(20) },
  ];
  for (const item of planned) await api.createEvent(item.title, item.date);

  // Export through the UI and keep the downloaded file.
  await page.goto('/settings');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export my data' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^hoje-export-\d{4}-\d{2}-\d{2}\.json$/);
  const exported = await readFile(await download.path());
  const upload = {
    name: download.suggestedFilename(),
    mimeType: 'application/json',
    buffer: exported,
  };

  // A second, fresh account in its own browser context imports it (merge).
  const context = await browser.newContext({
    baseURL: base,
    viewport: { width: 1440, height: 900 },
  });
  try {
    const other = await context.newPage();
    await registerUser(other, base);
    await other.goto('/settings');
    await other.getByLabel('Export file to import').setInputFiles(upload);
    await expect(other.getByRole('heading', { name: /^What importing hoje-export/ })).toBeVisible();
    await expect(other.getByText('3 to add, 0 already there (skipped)')).toBeVisible();
    await other.getByRole('button', { name: 'Import', exact: true }).click();
    await expect(other.getByText(/^Import finished: 3 events/)).toBeVisible();

    await other.goto('/');
    for (const item of planned) {
      await expect(other.locator(`[data-date="${item.date}"] .cal-ev`)).toHaveText(item.title);
    }

    // Importing the same file again changes nothing: everything is a duplicate.
    await other.goto('/settings');
    await other.getByLabel('Export file to import').setInputFiles(upload);
    await expect(other.getByText('0 to add, 3 already there (skipped)')).toBeVisible();
  } finally {
    await context.close();
  }
});

test('the import route takes up to 10 MB while other routes stay at 1 MB', async ({ api }) => {
  const notes = 'n'.repeat(4000);
  const events = Array.from({ length: 1300 }, (_, i) => ({
    category: 'a',
    title: `Bulk ${i}`,
    notes,
    start_date: '2026-05-04',
  }));
  const document = {
    format: 'hoje-export',
    version: 1,
    categories: [{ key: 'a', name: 'Bulk', colour: 'blue' }],
    events,
  };
  const body = JSON.stringify({ mode: 'merge', dry_run: true, data: document });
  expect(body.length).toBeGreaterThan(5_000_000);
  const json = { 'Content-Type': 'application/json' };

  // 5 MB of valid import: through Caddy and the API, a dry run answers 200.
  const accepted = await api.post('/api/v1/import', body, json);
  expect(accepted.status(), (await accepted.text()).slice(0, 200)).toBe(200);
  expect(((await accepted.json()) as { events: { create: number } }).events.create).toBe(1300);

  // The same 5 MB anywhere else is refused with 413.
  const elsewhere = await api.post('/api/v1/events', body, json);
  expect(elsewhere.status()).toBe(413);

  // More than 10 MB is refused on the import route too.
  const tooBig = await api.post('/api/v1/import', ' '.repeat(10_500_000), json);
  expect(tooBig.status()).toBe(413);
});

test('imports an .ics calendar file through the UI, and importing it again adds nothing', async ({
  page,
  account,
}) => {
  expect(account.email).toBeTruthy(); // registers the user the page is logged in as
  const stamp = Date.now();
  const first = dateInCurrentMonth(8);
  const second = dateInCurrentMonth(9);
  const compact = (iso: string) => iso.replaceAll('-', '');
  const ics = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//e2e//EN',
    'BEGIN:VEVENT',
    `UID:a-${stamp}`,
    `SUMMARY:Planning ${stamp}`,
    `DTSTART;VALUE=DATE:${compact(first)}`,
    'END:VEVENT',
    'BEGIN:VEVENT',
    `UID:b-${stamp}`,
    `SUMMARY:Retro ${stamp}`,
    `DTSTART;VALUE=DATE:${compact(second)}`,
    'END:VEVENT',
    'END:VCALENDAR',
    '',
  ].join('\r\n');
  const upload = { name: 'team.ics', mimeType: 'text/calendar', buffer: Buffer.from(ics) };

  await page.goto('/settings');
  await page.getByLabel('Calendar file to import').setInputFiles(upload);
  await expect(
    page.getByRole('heading', { name: 'What importing team.ics would do' }),
  ).toBeVisible();
  await expect(page.getByText('2 to add, 0 already there (skipped)')).toBeVisible();
  await page.getByLabel('Add the events to this category').fill('Team');
  await expect(page.getByText('1 new, 0 matched to existing')).toBeVisible();
  const card = page.locator('section[aria-labelledby="ics-preview-heading"]');
  await expect(card.getByRole('button', { name: 'Import', exact: true })).toBeEnabled();
  await card.getByRole('button', { name: 'Import', exact: true }).click();
  await expect(page.getByText(/^Import finished: 2 events and 1 category added/)).toBeVisible();

  await page.goto('/');
  await expect(page.locator(`[data-date="${first}"] .cal-ev`)).toHaveText(`Planning ${stamp}`);
  await expect(page.locator(`[data-date="${second}"] .cal-ev`)).toHaveText(`Retro ${stamp}`);

  await page.goto('/settings');
  await page.getByLabel('Calendar file to import').setInputFiles(upload);
  await page.getByLabel('Add the events to this category').fill('Team');
  await expect(page.getByText('0 to add, 2 already there (skipped)')).toBeVisible();
});

test('the .ics import route takes up to 10 MB like the data import route', async ({ api }) => {
  const description = 'n'.repeat(4000);
  const events = Array.from({ length: 1300 }, (_, i) =>
    [
      'BEGIN:VEVENT',
      `UID:bulk-${i}`,
      `SUMMARY:Bulk ${i}`,
      'DTSTART;VALUE=DATE:20260504',
      `DESCRIPTION:${description}`,
      'END:VEVENT',
    ].join('\r\n'),
  );
  const ics = `BEGIN:VCALENDAR\r\nVERSION:2.0\r\n${events.join('\r\n')}\r\nEND:VCALENDAR\r\n`;
  const body = JSON.stringify({ ics, dry_run: true });
  expect(body.length).toBeGreaterThan(5_000_000);
  const json = { 'Content-Type': 'application/json' };

  const accepted = await api.post('/api/v1/import/ics', body, json);
  expect(accepted.status(), (await accepted.text()).slice(0, 200)).toBe(200);
  expect(((await accepted.json()) as { events: { create: number } }).events.create).toBe(1300);

  const tooBig = await api.post('/api/v1/import/ics', ' '.repeat(10_500_000), json);
  expect(tooBig.status()).toBe(413);
});
