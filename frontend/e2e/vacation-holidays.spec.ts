import { expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop grid only');

const pad = (n: number) => String(n).padStart(2, '0');
const iso = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;

/** Monday and Friday (ISO dates) of the week containing `y-m-d`. */
function workWeek(y: number, m: number, d: number): [string, string] {
  const date = new Date(y, m - 1, d);
  const monday = new Date(y, m - 1, d - ((date.getDay() + 6) % 7));
  const friday = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 4);
  const fmt = (x: Date) => iso(x.getFullYear(), x.getMonth() + 1, x.getDate());
  return [fmt(monday), fmt(friday)];
}

test('holidays show in the grid and vacation days are counted in working days', async ({
  page,
  account,
  api,
}) => {
  void account;
  const year = new Date().getFullYear();
  await page.goto('/settings');

  // Enable Portugal.
  const portugal = page.getByRole('checkbox', { name: 'Portugal' });
  await expect(portugal).toBeVisible();
  await portugal.click();
  await expect(portugal).toBeChecked();

  // Allowance 22 for this year.
  const allowance = page.getByLabel('Allowance (days)');
  await allowance.fill('22');
  await allowance.press('Enter');
  await expect(page.getByText('Saved')).toBeVisible();

  const vacation = (await api.categories()).find((c) => c.name === 'Vacation');
  expect(vacation).toBeTruthy();

  // Mon-Fri in July: no PT holiday, 5 working days.
  const [julyMon, julyFri] = workWeek(year, 7, 14);
  await api.createEvent('Summer', julyMon, { end_date: julyFri, category_id: vacation?.id });

  await page.goto('/');
  await expect(page.locator(`[data-date="${year}-04-25"] .cal-hol`)).toHaveText('Freedom Day');
  await expect(page.getByRole('button', { name: 'Vacation: 17 left' })).toBeVisible();

  // A week containing a PT weekday holiday counts one day less.
  const candidate = ['12-08', '12-01', '11-01', '10-05', '06-10']
    .map((md) => [Number(md.slice(0, 2)), Number(md.slice(3))] as const)
    .find(([m, d]) => {
      const dow = new Date(year, m - 1, d).getDay();
      return dow >= 1 && dow <= 5;
    });
  expect(candidate).toBeTruthy();
  const [m, d] = candidate ?? [12, 8];
  const [holMon, holFri] = workWeek(year, m, d);
  await api.createEvent('Break', holMon, { end_date: holFri, category_id: vacation?.id });

  await page.reload();
  await expect(page.getByRole('button', { name: 'Vacation: 13 left' })).toBeVisible();
});
