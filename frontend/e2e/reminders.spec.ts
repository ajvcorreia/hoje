import { expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop only');

const MAILPIT = process.env.E2E_MAILPIT_URL ?? 'http://e2e-mailpit:8025';

interface MailpitMessage {
  ID: string;
  Subject: string;
  To: { Address: string }[];
}

async function remindersFor(
  request: import('@playwright/test').APIRequestContext,
  recipient: string,
  title: string,
): Promise<MailpitMessage[]> {
  const res = await request.get(`${MAILPIT}/api/v1/messages`);
  expect(res.ok()).toBeTruthy();
  const { messages } = (await res.json()) as { messages: MailpitMessage[] };
  return messages.filter(
    (m) =>
      m.Subject.startsWith('Reminder:') &&
      m.Subject.includes(title) &&
      m.To.some((t) => t.Address.toLowerCase() === recipient.toLowerCase()),
  );
}

test('a timed reminder arrives exactly once and shows in Recent emails', async ({
  page,
  api,
  account,
  request,
}) => {
  test.setTimeout(240_000);
  const title = `Standup ${Date.now()}`;
  const start = new Date(Date.now() + 2 * 60_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  const date = `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`;
  const time = `${pad(start.getHours())}:${pad(start.getMinutes())}`;
  const end = new Date(start.getTime() + 30 * 60_000);
  const endDate = `${end.getFullYear()}-${pad(end.getMonth() + 1)}-${pad(end.getDate())}`;
  await api.createEvent(title, date, {
    end_date: endDate,
    all_day: false,
    start_time: time,
    end_time: `${pad(end.getHours())}:${pad(end.getMinutes())}`,
    // The browser and the event share one zone, so "start" means the same instant everywhere.
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    reminders: [{ offset_minutes: 1 }],
  });

  await expect
    .poll(async () => (await remindersFor(request, account.email, title)).length, {
      timeout: 150_000,
      intervals: [2_000],
      message: 'the reminder email should arrive in Mailpit',
    })
    .toBeGreaterThanOrEqual(1);

  // Still exactly one after the worker has had several more cycles.
  await page.waitForTimeout(10_000);
  const mails = await remindersFor(request, account.email, title);
  expect(mails).toHaveLength(1);
  expect(mails[0]?.Subject).toContain(`Reminder: ${title}`);

  await page.goto('/settings');
  const list = page.getByRole('list', { name: 'Recent emails' });
  await expect(list).toBeVisible();
  const item = list.getByRole('listitem').filter({ hasText: `Reminder: ${title}` });
  await expect(item).toHaveCount(1);
  await expect(item).toContainText('Sent');
});
