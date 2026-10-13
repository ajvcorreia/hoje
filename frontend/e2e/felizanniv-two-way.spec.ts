import type { APIRequestContext, Page } from '@playwright/test';
import { Api, dateInCurrentMonth, expect, registerUser, test } from './fixtures';

// Two Hoje accounts share one FelizAnniv (deploy/e2e/fake_felizanniv.py): a change made in
// either one has to reach the other through it. The key has its own people, so this spec does not
// disturb the others.
const FAKE_URL = 'http://10.231.77.10:4000';
const KEY = 'fa_live_e2e_fake_key_twoway_0001';
const ADA = "Ada Lovelace's birthday";
const ADA_RENAMED = "Ada King's birthday";
const ZED = "Zed's birthday";

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

interface Status {
  last_sync_at: string | null;
}

async function connect(page: Page): Promise<void> {
  await page.goto('/settings');
  const section = page.getByRole('region', { name: 'FelizAnniv birthdays' });
  await section.getByLabel('FelizAnniv address').fill(FAKE_URL);
  await section.getByLabel('API key').fill(KEY);
  await section.getByRole('button', { name: 'Save & test' }).click();
  await expect(section.getByText(/Last synced .* · 2 birthdays/)).toBeVisible({ timeout: 20_000 });
}

async function apiFor(request: APIRequestContext, base: string): Promise<Api> {
  const state = await request.get('/api/v1/auth/state');
  const { csrf_token: csrf } = (await state.json()) as { csrf_token: string };
  return new Api(request, new URL(base).origin, csrf);
}

async function lastSync(request: APIRequestContext): Promise<string | null> {
  const res = await request.get('/api/v1/integrations/felizanniv');
  expect(res.ok()).toBeTruthy();
  return ((await res.json()) as Status).last_sync_at;
}

/** An edit asks for a sync within seconds (20 s, then the 2 s worker pass): wait until it ran. */
async function waitForNextSync(request: APIRequestContext, before: string | null): Promise<void> {
  await expect
    .poll(() => lastSync(request), { timeout: 60_000, intervals: [1000], message: 'a sync' })
    .not.toBe(before);
}

async function syncNow(api: Api): Promise<void> {
  const res = await api.post('/api/v1/integrations/felizanniv/sync', undefined);
  expect(res.status(), await res.text()).toBe(202);
}

async function isLinked(request: APIRequestContext, eventId: string): Promise<boolean> {
  const res = await request.get(`/api/v1/events/${eventId}`);
  expect(res.ok()).toBeTruthy();
  return ((await res.json()) as { felizanniv: boolean }).felizanniv;
}

async function titlesOn(api: Api, date: string): Promise<string[]> {
  return (await api.events(date, date)).map((e) => e.title);
}

/** Opens the event of that title from its day cell and returns the editor. */
async function openEvent(page: Page, date: string, title: string) {
  await page.goto('/');
  await page.locator(`[data-date="${date}"]`).click();
  await page
    .getByRole('dialog', { name: /^Events on / })
    .getByRole('button', { name: title })
    .click();
  const editor = page.getByRole('dialog', { name: 'Edit event' });
  await expect(editor.getByLabel('Title')).toHaveValue(title);
  return editor;
}

test('birthdays are events that sync both ways through FelizAnniv', async ({
  page,
  api,
  browser,
  baseURL,
}) => {
  test.setTimeout(300_000);
  const base = baseURL ?? '';
  const adaDate = dateInCurrentMonth(15);
  const zedDate = `${new Date().getFullYear()}-04-05`;

  await connect(page);
  const contextB = await browser.newContext({
    baseURL: base,
    viewport: { width: 1440, height: 900 },
  });
  try {
    // A second account, with its own session, on the same FelizAnniv.
    const pageB = await contextB.newPage();
    await registerUser(pageB, base);
    const apiB = await apiFor(contextB.request, base);
    await connect(pageB);
    expect(await titlesOn(apiB, adaDate)).toContain(ADA);

    // Hoje (A) -> FelizAnniv -> Hoje (B): a yearly all-day event in the Birthdays category is a
    // new person there, and the other account gets it as an event.
    const birthdays = (await api.categories()).find((c) => c.name === 'Birthdays');
    expect(birthdays).toBeDefined();
    const zed = await api.createEvent(ZED, zedDate, {
      category_id: birthdays?.id,
      repeat: 'yearly',
    });
    await expect
      .poll(() => isLinked(page.context().request, zed.id), {
        timeout: 60_000,
        intervals: [1000],
        message: 'the new birthday to reach FelizAnniv',
      })
      .toBe(true);
    await syncNow(apiB);
    await expect
      .poll(() => titlesOn(apiB, zedDate), { timeout: 30_000, intervals: [1000] })
      .toContain(ZED);

    // Hoje (B) -> FelizAnniv -> Hoje (A): renaming a birthday in the editor.
    const editorB = await openEvent(pageB, adaDate, ADA);
    const beforeB = await lastSync(contextB.request);
    await editorB.getByLabel('Title').fill(ADA_RENAMED);
    await editorB.getByRole('button', { name: 'Save' }).click();
    await expect(editorB).toBeHidden();
    await waitForNextSync(contextB.request, beforeB);
    await syncNow(api);
    await expect
      .poll(() => titlesOn(api, adaDate), { timeout: 30_000, intervals: [1000] })
      .toContain(ADA_RENAMED);
    expect(await titlesOn(api, adaDate)).not.toContain(ADA); // the same event, not a second one

    // Deleting a birthday in Hoje (A) deletes the person, and so the event in Hoje (B).
    const editorA = await openEvent(page, zedDate, ZED);
    const beforeA = await lastSync(page.context().request);
    await editorA.getByRole('button', { name: 'Delete' }).click();
    await expect(editorA).toBeHidden();
    await waitForNextSync(page.context().request, beforeA);
    await syncNow(apiB);
    await expect
      .poll(() => titlesOn(apiB, zedDate), { timeout: 30_000, intervals: [1000] })
      .not.toContain(ZED);
  } finally {
    await contextB.close();
  }
});
