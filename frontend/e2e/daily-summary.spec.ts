import { expect, test, todayIso } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop only');

const MAILPIT = process.env.E2E_MAILPIT_URL ?? 'http://e2e-mailpit:8025';

interface MailpitSummary {
  ID: string;
  To: { Address: string }[];
}

interface MailpitMessage {
  Subject: string;
  Text: string;
  HTML: string;
}

/** Full messages sent to `recipient` whose text says it is a test summary. */
async function testSummaries(
  request: import('@playwright/test').APIRequestContext,
  recipient: string,
): Promise<MailpitMessage[]> {
  const list = await request.get(`${MAILPIT}/api/v1/messages`);
  expect(list.ok()).toBeTruthy();
  const { messages } = (await list.json()) as { messages: MailpitSummary[] };
  const found: MailpitMessage[] = [];
  for (const m of messages) {
    if (!m.To.some((t) => t.Address.toLowerCase() === recipient.toLowerCase())) continue;
    const full = await request.get(`${MAILPIT}/api/v1/message/${m.ID}`);
    const message = (await full.json()) as MailpitMessage;
    if (message.Subject.startsWith('Hoje — ') && message.Text.includes('test summary')) {
      found.push(message);
    }
  }
  return found;
}

function tomorrowIso(): string {
  const [y, m, d] = todayIso().split('-').map(Number);
  const next = new Date(y ?? 1970, (m ?? 1) - 1, (d ?? 1) + 1);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`;
}

test('a test summary lists today and tomorrow and never injects HTML from titles', async ({
  page,
  api,
  account,
  request,
}) => {
  test.setTimeout(120_000);
  // "Today" is decided in the user's time zone: make it the browser's.
  await api.patchMe({ timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
  const stamp = Date.now();
  const todayTitle = `Planning ${stamp}`;
  const tomorrowTitle = `Offsite <b>x</b> ${stamp}`;
  await api.createEvent(todayTitle, todayIso());
  await api.createEvent(tomorrowTitle, tomorrowIso());

  await page.goto('/settings');
  const toggle = page.getByRole('checkbox', { name: 'Send me a daily summary email' });
  const time = page.getByLabel('Send at');
  await expect(toggle).not.toBeChecked();
  await expect(time).toBeDisabled();
  await toggle.click();
  await expect(toggle).toBeChecked();
  await expect(time).toBeEnabled();
  await expect(page.getByText(/Time zone: /)).toBeVisible();

  await page.getByRole('button', { name: 'Send a test summary' }).click();
  await expect(page.getByText(/Test summary sent/)).toBeVisible();

  await expect
    .poll(async () => (await testSummaries(request, account.email)).length, {
      timeout: 60_000,
      intervals: [1_000],
      message: 'the test summary should arrive in Mailpit',
    })
    .toBeGreaterThanOrEqual(1);
  const [message] = await testSummaries(request, account.email);
  expect(message).toBeDefined();
  expect(message?.Subject).toMatch(/^Hoje — \w+ \d+ \w+: 1 event today$/);
  for (const body of [message?.Text ?? '', message?.HTML ?? '']) {
    expect(body).toContain(todayTitle);
    expect(body.toLowerCase()).toContain('changes since');
    expect(body.toLowerCase()).toContain('today');
    expect(body.toLowerCase()).toContain('tomorrow');
  }
  // Plain text keeps the title as typed; HTML escapes it, so no tag reaches the reader.
  expect(message?.Text).toContain(tomorrowTitle);
  expect(message?.HTML).toContain('Offsite &lt;b&gt;x&lt;/b&gt;');
  expect(message?.HTML).not.toContain('<b>x</b>');

  // The settings page remembers the choice and lists the email as a daily summary.
  await page.reload();
  await expect(page.getByRole('checkbox', { name: 'Send me a daily summary email' })).toBeChecked();
  const item = page
    .getByRole('list', { name: 'Recent emails' })
    .getByRole('listitem')
    .filter({ hasText: 'Daily summary' });
  await expect(item.first()).toContainText('Sent');
});
