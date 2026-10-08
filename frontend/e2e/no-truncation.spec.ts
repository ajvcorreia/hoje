import type { Page } from '@playwright/test';
import { type Api, dateInCurrentMonth, expect, test } from './fixtures';

// Names of events, holidays and birthdays are never cut off, shortened or ellipsized: not in the
// month grid, not in the rotated labels, not in the popover, agenda or search results.
test.skip(({ isMobile }) => isMobile, 'desktop only');

const FAKE_URL = 'http://10.231.77.10:4000';
const FAKE_KEY = 'fa_live_e2e_fake_key_0123456789';

const LONG = 'Quarterly stakeholder alignment workshop with the extended leadership team';
const WIDE = 'WWWWWWWW MMMMMMMM WMWMWMWM';
const ACCENTS = 'Ação de formação – Coração Ünïcödé Řěžňý ÀÉÎÕÜ';
const CJK = '年度総括会議と来年度の計画策定ミーティング 会议';
const EMOJI = '🎉🎂🎈 Party 🥳🎁';
const NO_SPACES = 'Supercalifragilisticexpialidocious_Supercalifragilisticexpialidocious';
const PUNCT = 'Dr. O’Neil, Q&A (re: "budget") / 50% off #1';

interface Planned {
  title: string;
  day: number;
  end?: number;
  vertical?: boolean;
}

/** Titles of every kind, on days with 1..6 events, with and without rotated multi-day labels. */
const BUSY: Planned[] = [
  { title: LONG, day: 2 },
  { title: WIDE, day: 3 },
  { title: ACCENTS, day: 3 },
  { title: CJK, day: 4 },
  { title: EMOJI, day: 4 },
  { title: 'A', day: 4 },
  { title: 'Go', day: 5 },
  // Short blocks with long names: the rotated label cannot fit, so it must become horizontal.
  { title: 'Quarterly stakeholder alignment', day: 6, end: 7, vertical: true },
  { title: WIDE, day: 8, end: 9, vertical: true },
  // Long blocks: the name shrinks (and rotates) to fit.
  { title: LONG, day: 11, end: 18, vertical: true },
  { title: 'Conference', day: 11, end: 18 },
  { title: 'Short', day: 13, end: 14, vertical: true },
  // Horizontal multi-day blocks.
  { title: ACCENTS, day: 20, end: 21 },
  { title: NO_SPACES, day: 22 },
  { title: PUNCT, day: 22 },
  // Six events on one day.
  ...[
    'Alpha team sync',
    'Bravo budget review',
    'Charlie planning',
    'Delta retro',
    'Echo',
    'Foxtrot',
  ].map((title) => ({ title, day: 24 })),
  { title: 'Lisbon conference', day: 26, end: 28, vertical: true },
];

async function seed(api: Api, plan: readonly Planned[]) {
  for (const p of plan) {
    await api.createEvent(p.title, dateInCurrentMonth(p.day), {
      end_date: dateInCurrentMonth(p.end ?? p.day),
      ...(p.vertical ? { label_vertical: true } : {}),
    });
  }
}

/** Every title-bearing element of the month grid, checked in the browser. Returns problems. */
async function gridProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const problems: string[] = [];
    const lengthOf = (el: Element) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      return range.getBoundingClientRect();
    };
    const near = (a: number, b: number) => a <= b + 1;
    for (const el of Array.from(
      document.querySelectorAll<HTMLElement>('.cal-ev, .cal-hol, .cal-vlabel-text'),
    )) {
      const text = (el.textContent ?? '').trim();
      if (!text) continue;
      const name = `${el.className} "${text}"`;
      const style = getComputedStyle(el);
      if (style.textOverflow === 'ellipsis') problems.push(`${name}: text-overflow ellipsis`);
      if (!near(el.scrollWidth, el.clientWidth)) {
        problems.push(`${name}: scrollWidth ${el.scrollWidth} > clientWidth ${el.clientWidth}`);
      }
      if (!near(el.scrollHeight, el.clientHeight)) {
        problems.push(`${name}: scrollHeight ${el.scrollHeight} > clientHeight ${el.clientHeight}`);
      }
      // Exact: the text run must fit the content box, to the sub-pixel (scrollWidth is rounded).
      const box = el.getBoundingClientRect();
      const run = lengthOf(el);
      const px = (v: string) => parseFloat(v) || 0;
      if (style.writingMode.startsWith('horizontal')) {
        const room =
          box.width -
          px(style.paddingLeft) -
          px(style.paddingRight) -
          px(style.borderLeftWidth) -
          px(style.borderRightWidth);
        if (run.width > room + 0.05) problems.push(`${name}: text ${run.width} wide, room ${room}`);
      } else {
        const room = box.height - px(style.paddingTop) - px(style.paddingBottom);
        if (run.height > room + 0.05)
          problems.push(`${name}: text ${run.height} tall, room ${room}`);
      }
      // The painted text must also lie inside the box that would clip it.
      const host = el.closest('.cal-cell') ?? el.closest('.cal-vlabel');
      if (host) {
        const t = lengthOf(el);
        const h = host.getBoundingClientRect();
        if (
          t.left < h.left - 1 ||
          t.right > h.right + 1 ||
          t.top < h.top - 1 ||
          t.bottom > h.bottom + 1
        ) {
          problems.push(
            `${name}: text ${Math.round(t.left)}-${Math.round(t.right)} x ${Math.round(t.top)}-${Math.round(t.bottom)} outside ${Math.round(h.left)}-${Math.round(h.right)} x ${Math.round(h.top)}-${Math.round(h.bottom)}`,
          );
        }
      }
    }
    for (const cell of Array.from(document.querySelectorAll<HTMLElement>('.cal-cell'))) {
      if (cell.scrollWidth > cell.clientWidth + 1) {
        problems.push(
          `cell ${cell.dataset.date}: scrollWidth ${cell.scrollWidth} > ${cell.clientWidth}`,
        );
      }
      // The "+N" chip must not sit on top of a title.
      const chip = cell.querySelector('.cal-more');
      if (!chip) continue;
      const c = chip.getBoundingClientRect();
      for (const el of Array.from(cell.querySelectorAll('.cal-ev, .cal-hol'))) {
        if (!(el.textContent ?? '').trim()) continue;
        const t = lengthOf(el);
        if (t.left < c.right && t.right > c.left && t.top < c.bottom && t.bottom > c.top) {
          problems.push(`cell ${cell.dataset.date}: chip overlaps "${el.textContent}"`);
        }
      }
    }
    return problems;
  });
}

/** Text of every title element currently drawn in the grid (horizontal and rotated). */
async function drawnTitles(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('.cal-ev, .cal-hol, .cal-vlabel-text'))
      .map((el) => (el.textContent ?? '').trim())
      .filter(Boolean),
  );
}

async function expectNoTruncation(page: Page, mustShow: readonly string[] = []) {
  await expect(page.locator('.cal-scroll')).toBeVisible();
  // Let fonts, the first measurement and the row-height observer settle.
  await page.evaluate(() => document.fonts.ready);
  await expect.poll(() => drawnTitles(page).then((t) => t.length)).toBeGreaterThan(0);
  await page.waitForTimeout(150);
  expect(await gridProblems(page)).toEqual([]);
  const drawn = await drawnTitles(page);
  for (const title of mustShow) expect(drawn, `"${title}" drawn in full`).toContain(title);
  // Nothing is clipped by a scroll container: all 37 rows fit without vertical scrolling.
  const scroll = page.locator('.cal-scroll');
  await expect
    .poll(() => scroll.evaluate((el) => el.scrollHeight - el.clientHeight))
    .toBeLessThanOrEqual(1);
}

async function prefs(page: Page, values: Record<string, string>) {
  await page.addInitScript((entries) => {
    for (const [k, v] of Object.entries(entries)) window.localStorage.setItem(k, v);
  }, values);
}

// Single-day titles that are on days with at most two events, so they are drawn at the default setting.
const VISIBLE = BUSY.filter(
  (p) => !p.vertical && p.end === undefined && p.day !== 24 && p.day !== 4,
);

test.describe('month grid, default settings', () => {
  test('every kind of single-day title is drawn whole', async ({ page, api }) => {
    await seed(api, BUSY);
    await page.goto('/');
    await expectNoTruncation(
      page,
      VISIBLE.map((p) => p.title),
    );
  });

  test('1..6 events on one day with wide characters', async ({ page, api }) => {
    const titles = [LONG, WIDE, ACCENTS, CJK, EMOJI, NO_SPACES];
    for (let n = 1; n <= 6; n += 1) {
      for (const t of titles.slice(0, n)) await api.createEvent(t, dateInCurrentMonth(n));
    }
    await page.goto('/');
    await expectNoTruncation(page);
  });

  test('freshly loaded page measures the final font before painting', async ({ page, api }) => {
    await seed(api, BUSY);
    // Check as early as possible: right after the grid appears, without waiting for fonts.
    await page.goto('/', { waitUntil: 'commit' });
    await expect(page.locator('.cal-cell').first()).toBeVisible();
    await expect.poll(() => drawnTitles(page).then((t) => t.length)).toBeGreaterThan(5);
    expect(await gridProblems(page)).toEqual([]);
    await page.evaluate(() => document.fonts.ready);
    expect(await gridProblems(page)).toEqual([]);
  });

  test('re-measures when the font changes after load', async ({ page, api }) => {
    await seed(api, BUSY);
    await page.goto('/');
    await expectNoTruncation(page);
    for (const family of ['Courier New, monospace', 'Georgia, serif', 'Verdana, sans-serif']) {
      await page.evaluate((f) => {
        document.documentElement.style.fontFamily = f;
      }, family);
      await page.waitForTimeout(300);
      expect(await gridProblems(page), family).toEqual([]);
    }
  });

  test('window resize keeps names whole', async ({ page, api }) => {
    await seed(api, BUSY);
    await page.goto('/');
    await expectNoTruncation(page);
    for (const [width, height] of [
      [1280, 720],
      [1440, 1000],
      [1100, 600],
    ] as const) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(300);
      expect(await gridProblems(page), `${width}x${height}`).toEqual([]);
    }
  });
});

test.describe('events per day setting', () => {
  for (const n of [1, 2, 3, 4, 5, 6]) {
    test(`max_events_per_day = ${n}`, async ({ page, api }) => {
      await api.patchMe({ max_events_per_day: n });
      await seed(api, BUSY);
      await page.goto('/');
      await expectNoTruncation(page);
    });
  }
});

test.describe('text size, week numbers and window width', () => {
  for (const size of ['small', 'default', 'large', 'xlarge']) {
    for (const width of [1280, 1440]) {
      for (const weeks of ['on', 'off']) {
        test(`${size} text, ${width}px wide, week numbers ${weeks}`, async ({ page, api }) => {
          await page.setViewportSize({ width, height: 900 });
          await prefs(page, { 'hoje.textSize': size, 'hoje.weekNumbers': weeks });
          await api.patchMe({ max_events_per_day: 3 });
          await seed(api, BUSY);
          await page.goto('/');
          await expectNoTruncation(page);
        });
      }
    }
  }

  test('changing the text size in the running app re-measures', async ({ page, api }) => {
    await seed(api, BUSY);
    await page.goto('/');
    await expectNoTruncation(page);
    for (const size of ['xlarge', 'small', 'large']) {
      await page.evaluate((s) => document.documentElement.setAttribute('data-text-size', s), size);
      await page.waitForTimeout(300);
      expect(await gridProblems(page), size).toEqual([]);
    }
  });
});

test.describe('multi-day blocks', () => {
  test('rotated labels are never cut: they shrink to a readable size or turn horizontal', async ({
    page,
    api,
  }) => {
    // Six names side by side (six lanes) in blocks of 2, 3, 5 and 8 days.
    await api.patchMe({ max_events_per_day: 6 });
    const names = ['Erbil', 'Lisbon conference', LONG, WIDE, CJK, NO_SPACES];
    const grid: Planned[] = [];
    let start = 1;
    for (const len of [2, 3, 5, 8]) {
      for (const title of names)
        grid.push({ title, day: start, end: start + len - 1, vertical: true });
      start += len + 1;
    }
    await seed(api, grid);
    await page.goto('/');
    await expectNoTruncation(page);
    // Whatever was rotated or not, every name is in the DOM in full.
    const drawn = await drawnTitles(page);
    for (const p of grid) expect(drawn).toContain(p.title);
  });

  test('a block that crosses the month boundary', async ({ page, api }) => {
    const now = new Date();
    const next = new Date(now.getFullYear(), now.getMonth() + 1, 4);
    const end = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-04`;
    await api.createEvent(LONG, dateInCurrentMonth(27), { end_date: end, label_vertical: true });
    await api.createEvent('Short trip', dateInCurrentMonth(27), { end_date: end });
    await page.goto('/');
    await expectNoTruncation(page);
  });

  test('vertical labels on days that also carry a holiday-less overlay and a +N chip', async ({
    page,
    api,
  }) => {
    await api.patchMe({ max_events_per_day: 2 });
    await seed(api, [
      { title: LONG, day: 5, end: 9, vertical: true },
      { title: 'Second lane block with a long name', day: 5, end: 7, vertical: true },
      { title: 'Third', day: 6 },
      { title: 'Fourth overflow item', day: 6 },
      { title: 'Fifth overflow item', day: 6 },
    ]);
    await page.goto('/');
    await expectNoTruncation(page);
  });
});

test.describe('holidays and birthdays', () => {
  test('long holiday names on empty days and on days with events', async ({ page, api }) => {
    const year = new Date().getFullYear();
    await page.goto('/settings');
    const portugal = page.getByRole('checkbox', { name: 'Portugal' });
    await expect(portugal).toBeVisible();
    await portugal.click();
    await expect(portugal).toBeChecked();

    for (const [month, day] of [
      [6, 10],
      [4, 25],
      [12, 8],
    ] as const) {
      const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      await api.createEvent(LONG, date);
      await api.createEvent(WIDE, date);
    }
    await api.createEvent('Solo on a holiday', `${year}-05-01`);
    await page.goto('/');
    await expect(page.locator('.cal-hol').first()).toBeVisible();
    expect(await page.locator('.cal-hol').count()).toBeGreaterThan(5);
    await expectNoTruncation(page);
  });

  test('holidays with large text and week numbers at 1280px', async ({ page, api }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await prefs(page, { 'hoje.textSize': 'xlarge', 'hoje.weekNumbers': 'on' });
    await page.goto('/settings');
    const portugal = page.getByRole('checkbox', { name: 'Portugal' });
    await portugal.click();
    await expect(portugal).toBeChecked();
    await api.createEvent(LONG, `${new Date().getFullYear()}-06-10`);
    await page.goto('/');
    await expect(page.locator('.cal-hol').first()).toBeVisible();
    await expectNoTruncation(page);
  });

  test('birthdays next to events', async ({ page, api }) => {
    await page.goto('/settings');
    const section = page.getByRole('region', { name: 'FelizAnniv birthdays' });
    await section.getByLabel('FelizAnniv address').fill(FAKE_URL);
    await section.getByLabel('API key').fill(FAKE_KEY);
    await section.getByRole('button', { name: 'Save & test' }).click();
    await expect(section.getByText(/Last synced .* · 2 birthdays/)).toBeVisible({
      timeout: 20_000,
    });
    // The fake birthday falls on the 15th of the current month.
    await api.createEvent(LONG, dateInCurrentMonth(15));
    await api.createEvent(WIDE, dateInCurrentMonth(15));
    await api.createEvent(ACCENTS, dateInCurrentMonth(15));
    await page.goto('/');
    await expect(page.locator('.cal-hol[data-birthday]').first()).toBeVisible();
    await expectNoTruncation(page);
  });
});

/** Text boxes inside `root` that are cut off, clipped by their parent or ellipsized. */
async function boxProblems(page: Page, rootSelector: string): Promise<string[]> {
  return page.evaluate((selector) => {
    const root = document.querySelector<HTMLElement>(selector);
    if (!root) return [`${selector}: not found`];
    const problems: string[] = [];
    const bounds = root.getBoundingClientRect();
    for (const el of Array.from(root.querySelectorAll<HTMLElement>('*'))) {
      const own = Array.from(el.childNodes).some(
        (n: ChildNode) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? '').trim() !== '',
      );
      if (!own || el.closest('.sr-only')) continue;
      const name = `<${el.tagName.toLowerCase()} class="${el.className}"> "${(el.textContent ?? '').trim()}"`;
      const style = getComputedStyle(el);
      if (style.textOverflow === 'ellipsis') problems.push(`${name}: text-overflow ellipsis`);
      if (style.display !== 'inline') {
        if (el.scrollWidth > el.clientWidth + 1) problems.push(`${name}: scrollWidth`);
        if (el.scrollHeight > el.clientHeight + 1) problems.push(`${name}: scrollHeight`);
      }
      const range = document.createRange();
      range.selectNodeContents(el);
      const t = range.getBoundingClientRect();
      if (t.left < bounds.left - 1 || t.right > bounds.right + 1) {
        problems.push(`${name}: outside ${selector}`);
      }
    }
    return problems;
  }, rootSelector);
}

test.describe('other views', () => {
  const NAMES = [LONG, WIDE, ACCENTS, CJK, EMOJI, NO_SPACES, PUNCT];

  test('day popover wraps long names', async ({ page, api }) => {
    for (const t of NAMES) await api.createEvent(t, dateInCurrentMonth(12));
    await page.goto('/');
    await page.locator(`[data-date="${dateInCurrentMonth(12)}"]`).click();
    const dialog = page.getByRole('dialog', { name: /^Events on / });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('listitem')).toHaveCount(NAMES.length);
    expect(await boxProblems(page, '[role="dialog"]')).toEqual([]);
    for (const t of NAMES) await expect(dialog.getByText(t, { exact: true })).toBeVisible();
  });

  test('day popover with a long holiday', async ({ page, api }) => {
    await page.goto('/settings');
    const portugal = page.getByRole('checkbox', { name: 'Portugal' });
    await portugal.click();
    await expect(portugal).toBeChecked();
    const date = `${new Date().getFullYear()}-06-10`;
    await api.createEvent(LONG, date);
    await page.goto('/');
    await page.locator(`[data-date="${date}"]`).click();
    await expect(page.getByRole('dialog', { name: /^Events on / })).toBeVisible();
    expect(await boxProblems(page, '[role="dialog"]')).toEqual([]);
  });

  test('search results wrap long names', async ({ page, api }) => {
    for (const t of NAMES) await api.createEvent(`Zebra ${t}`, dateInCurrentMonth(13));
    await page.goto('/');
    await page.getByLabel('Search events').fill('Zebra');
    const results = page.getByRole('list', { name: 'Search results' });
    await expect(results.getByRole('listitem')).toHaveCount(NAMES.length);
    expect(await boxProblems(page, '[aria-label="Search results"]')).toEqual([]);
  });

  test('agenda wraps long names', async ({ page, api }) => {
    const now = new Date();
    const when = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const date = `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}-${String(when.getDate()).padStart(2, '0')}`;
    for (const t of NAMES) await api.createEvent(t, date);
    await page.goto('/');
    await page.getByRole('button', { name: 'Agenda' }).click();
    for (const t of NAMES) await expect(page.getByText(t, { exact: true })).toBeVisible();
    expect(await boxProblems(page, 'main')).toEqual([]);
  });

  test('year view shows no clipped names', async ({ page, api }) => {
    for (const t of NAMES) await api.createEvent(t, dateInCurrentMonth(14));
    await page.goto('/');
    await page.getByRole('button', { name: 'Year', exact: true }).click();
    await expect(page.locator('.yr-day').first()).toBeVisible();
    expect(await boxProblems(page, 'main')).toEqual([]);
  });
});
