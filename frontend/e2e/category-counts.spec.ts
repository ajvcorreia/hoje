import { dateInCurrentMonth, expect, test } from './fixtures';

test.skip(({ isMobile }) => isMobile, 'desktop header only');

// Count = event occurrences of the category in the viewed year (a repeat counts once each).
test('category pills show the occurrence count, live, also while toggled off', async ({
  page,
  account,
  api,
}) => {
  void account;
  const year = new Date().getFullYear();
  const make = async (name: string, colour: string) => {
    const res = await api.post('/api/v1/categories', { name, colour });
    expect(res.status(), await res.text()).toBe(201);
    return ((await res.json()) as { id: string }).id;
  };
  const alpha = await make('Alpha cat', 'blue');
  const beta = await make('Beta cat', 'rose');
  await make('Gamma cat', 'lime');

  for (const day of [3, 4, 5]) {
    await api.createEvent(`A${day}`, `${year}-02-0${day}`, { category_id: alpha });
  }
  await api.createEvent('Monthly', `${year}-01-10`, { category_id: alpha, repeat: 'monthly' });
  await api.createEvent('B1', `${year}-03-03`, { category_id: beta });

  await page.goto('/');
  const group = page.getByRole('group', { name: 'Show categories' });
  const pill = (name: string) => group.getByRole('button', { name: new RegExp(`^${name},`) });

  await expect(pill('Alpha cat')).toHaveAccessibleName('Alpha cat, 15 events');
  await expect(pill('Alpha cat').getByTestId('category-count')).toHaveText('15');
  await expect(pill('Beta cat')).toHaveAccessibleName('Beta cat, 1 event');
  await expect(pill('Gamma cat')).toHaveAccessibleName('Gamma cat, 0 events');
  await expect(pill('Gamma cat').getByTestId('category-count')).toHaveText('0');
  await expect(pill('Alpha cat').getByText('Alpha cat', { exact: true })).toBeVisible();

  // An event added elsewhere (API) shows up through realtime / refetch.
  await api.createEvent('B2', dateInCurrentMonth(12), { category_id: beta });
  await expect(pill('Beta cat')).toHaveAccessibleName('Beta cat, 2 events', { timeout: 10_000 });

  // Toggling a pill off hides its events but keeps the number.
  await pill('Beta cat').click();
  await expect(pill('Beta cat')).toHaveAttribute('aria-pressed', 'false');
  await expect(pill('Beta cat')).toHaveAccessibleName('Beta cat, 2 events');
  await expect(pill('Beta cat').getByTestId('category-count')).toHaveText('2');
  await expect(page.locator('.cal-ev', { hasText: 'B2' })).toHaveCount(0);
});
