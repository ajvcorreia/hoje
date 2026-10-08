import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearMeasureCache,
  monthTracks,
  rotationRule,
  measurerFor,
  verticalPlan,
  verticalLaneWidth,
  DEFAULT_FIT_FONTS,
  type TextMeasurer,
} from './fitWidth';
import { layoutMonth, type LayoutInput } from './layout';

// 6px per character, no canvas needed.
const measure: TextMeasurer = {
  text: (v) => v.length * 6,
  italic: (v) => v.length * 6,
  chip: (v) => v.length * 5,
  lane: 16,
  // A name fits a rotated label when it has at most 4 characters per day of the block.
  plan: (title, days) =>
    title.length <= days * 4 ? { lines: [title], size: 12, width: 16 } : null,
};

const ev = (
  key: string,
  start: string,
  end: string,
  extra: Partial<LayoutInput> = {},
): LayoutInput => ({ key, start, end, allDay: true, title: key, ...extra });

const march = (inputs: LayoutInput[], maxEvents = 2, m: TextMeasurer = measure) =>
  layoutMonth(inputs, 2026, 2, maxEvents, rotationRule(m));
const none = new Map<number, string>();
const day = (d: number) => `2026-03-${String(d).padStart(2, '0')}`;
const vertical = (key: string, start: string, end: string) =>
  ev(key, start, end, { labelVertical: true });
const box = (title: string) => title.length * 6 + 8 + 1;

describe('rotationRule', () => {
  it('rotates a flagged block of 2+ days whose name fits, whatever else shares the days', () => {
    const rule = rotationRule(measure);
    expect(rule(vertical('abcd', day(1), day(2)), 2)).toBe(true);
    expect(rule(ev('abcd', day(1), day(2)), 2)).toBe(false);
    expect(rule(vertical('abcd', day(1), day(1)), 1)).toBe(false);
    expect(rule(vertical('abcdefghi', day(1), day(2)), 2)).toBe(false);
  });
});

describe('monthTracks', () => {
  it('needs the title of a single event plus padding, border and slack: one track', () => {
    const t = monthTracks(march([ev('lunch', day(10), day(10))]), none, measure);
    expect(t.days[9]?.items).toEqual([box('lunch')]);
    expect(t.width).toBe(box('lunch') + 4);
    expect(t.onlyVertical).toBe(false);
  });

  it('needs nothing in a month without text', () => {
    expect(monthTracks(march([]), none, measure)).toMatchObject({ width: 0, onlyVertical: false });
  });

  it('puts the events of a day side by side: one track per event, in packed order', () => {
    const t = monthTracks(
      march([ev('alpha', day(10), day(10)), ev('be', day(10), day(10))]),
      none,
      measure,
    );
    expect(t.days[9]?.items).toEqual([box('alpha'), box('be')]);
    expect(t.width).toBe(box('alpha') + box('be') + 4);
  });

  it('sets the column from its widest day; tracks are not shared between days', () => {
    const t = monthTracks(
      march([
        ev('aa', day(10), day(10)),
        ev('bb', day(10), day(10)),
        ev('cccccc', day(20), day(20)),
        ev('d', day(20), day(20)),
      ]),
      none,
      measure,
    );
    expect(t.days[9]?.items).toEqual([box('aa'), box('bb')]);
    expect(t.days[19]?.items).toEqual([box('cccccc'), box('d')]);
    expect(t.width).toBe(box('cccccc') + box('d') + 4);
  });

  it('adds the overlay text before the events on a day with events', () => {
    const t = monthTracks(march([ev('lunch', day(5), day(5))]), new Map([[5, 'Holiday']]), measure);
    expect(t.days[4]).toMatchObject({ overlay: 7 * 6 + 8, items: [box('lunch')] });
    expect(t.width).toBe(7 * 6 + 8 + box('lunch') + 4);
  });

  it('needs only the overlay text on an empty day', () => {
    const t = monthTracks(march([]), new Map([[5, 'Holiday']]), measure);
    expect(t.width).toBe(7 * 6 + 8 + 4);
    expect(t.days[4]?.items).toEqual([]);
  });

  it('adds a chip track when a day overflows', () => {
    const three = ['aa', 'bb', 'cc'].map((k) => ev(k, day(10), day(10)));
    const t = monthTracks(march(three), none, measure);
    expect(t.days[9]?.chip).toBe(2 * 5 + 12);
    expect(t.width).toBe(2 * box('aa') + (2 * 5 + 12) + 4);
  });

  it('works for up to six events', () => {
    const six = ['a', 'b', 'c', 'd', 'e', 'f'].map((k) => ev(k, day(10), day(10)));
    const t = monthTracks(march(six, 6), none, measure);
    expect(t.days[9]?.items).toHaveLength(6);
    expect(t.days[9]?.chip).toBe(0);
  });

  it('gives a continuation box without a title the minimum width', () => {
    const t = monthTracks(march([ev('trip', day(10), day(12))]), none, measure);
    expect(t.days[9]?.items).toEqual([box('trip')]);
    expect(t.days[10]?.items).toEqual([12]);
    expect(t.width).toBe(box('trip') + 4);
  });
});

describe('monthTracks with rotated labels', () => {
  it('needs one narrow column for a label that has its days to itself, not its text width', () => {
    const t = monthTracks(march([vertical('conf', day(10), day(12))]), none, measure);
    expect(t.days[9]).toMatchObject({ rotated: 1, items: [] });
    expect(t.width).toBe(16);
    expect(t.onlyVertical).toBe(true);
  });

  it('is the same for any title length that fits the block height', () => {
    const fits: TextMeasurer = {
      ...measure,
      plan: (title) => ({ lines: [title], size: 12, width: 16 }),
    };
    const t = monthTracks(
      march([vertical('A very long conference name', day(10), day(12))], 2, fits),
      none,
      fits,
    );
    expect(t.width).toBe(16);
  });

  it('turns a name that does not fit its block into a horizontal title that sets the width', () => {
    const title = 'A very long conference name';
    const t = monthTracks(march([vertical(title, day(10), day(12))]), none, measure);
    expect(t.days[9]?.rotated).toBe(0);
    expect(t.onlyVertical).toBe(false);
    expect(t.width).toBe(box(title) + 4);
  });

  it('decides per block: the same name rotates in a longer block', () => {
    const title = 'conference name';
    const short = monthTracks(march([vertical(title, day(10), day(11))]), none, measure);
    const long = monthTracks(march([vertical(title, day(10), day(13))]), none, measure);
    expect(short.days[9]?.rotated).toBe(0);
    expect(long.days[9]?.rotated).toBe(1);
    expect(long.width).toBe(16);
  });

  it('rotates a block even when it shares its days with a long horizontal title', () => {
    const t = monthTracks(
      march([vertical('abcd', day(10), day(11)), ev('lunch', day(10), day(10))]),
      none,
      measure,
    );
    // The rotated column stays 16px; only the horizontal title is as wide as its text.
    expect(t.days[9]).toMatchObject({ rotated: 1, items: [box('lunch')] });
    expect(t.width).toBe(16 + box('lunch') + 4);
  });

  it('counts only the part of a block inside the month', () => {
    const apr = (d: number) => `2026-04-${String(d).padStart(2, '0')}`;
    const t = monthTracks(
      layoutMonth([vertical('abcd', day(31), apr(3))], 2026, 2, 2, rotationRule(measure)),
      none,
      measure,
    );
    // One day left in March: a single day is not a block, so the title stays horizontal.
    expect(t.days[30]?.rotated).toBe(0);
  });

  it('gives each overlapping rotated label its own narrow column', () => {
    const t = monthTracks(
      march(
        [
          vertical('a', day(10), day(12)),
          vertical('b', day(10), day(12)),
          vertical('c', day(10), day(12)),
        ],
        4,
      ),
      none,
      measure,
    );
    expect(t.days[9]?.rotated).toBe(3);
    expect(t.width).toBe(48);
    expect(t.onlyVertical).toBe(true);
  });

  it('shares a column between rotated blocks that do not overlap', () => {
    const t = monthTracks(
      march([vertical('a', day(2), day(4)), vertical('b', day(5), day(7))], 4),
      none,
      measure,
    );
    expect(t.width).toBe(16);
  });

  it('keeps an empty spacer column below the highest rotated lane that covers the day', () => {
    const t = monthTracks(
      march([vertical('x', day(2), day(3)), vertical('y', day(3), day(6))], 4),
      none,
      measure,
    );
    // x sits in column 0 and y in column 1 (they overlap on day 3); from day 4 on column 0 is
    // free, but y keeps its x offset, so the day still has two columns.
    expect(t.days[1]?.rotated).toBe(1);
    expect(t.days[2]?.rotated).toBe(2);
    expect(t.days[3]?.rotated).toBe(2);
    expect(t.days[5]?.rotated).toBe(2);
  });

  it('adds the events next to the rotated column of the day', () => {
    const t = monthTracks(
      march([vertical('a', day(10), day(12)), ev('lunch', day(12), day(12))]),
      none,
      measure,
    );
    expect(t.days[11]).toMatchObject({ rotated: 1, items: [box('lunch')] });
    expect(t.width).toBe(16 + box('lunch') + 4);
    expect(t.onlyVertical).toBe(false);
  });
});

describe('verticalPlan', () => {
  const fonts = { rem: 16, family: 'test-sans' };

  beforeEach(() => {
    clearMeasureCache();
    // 0.6em per character at any font size.
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => {
      const ctx = {
        font: '',
        measureText(text: string) {
          const size = parseFloat(/(\d+(?:\.\d+)?)px/.exec(ctx.font)?.[1] ?? '10');
          return { width: text.length * size * 0.6 };
        },
      };
      return ctx as unknown as CanvasRenderingContext2D;
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearMeasureCache();
  });

  // Row height 17: a block of d days leaves 17 d - 12 px; one em of text is 0.62 x 1.03 per char.
  const plan = (title: string, days: number, f = fonts, size = 12) =>
    verticalPlan(title, days, 17, f, size);
  const longest = (title: string, days: number) =>
    Math.max(...(plan(title, days)?.lines.map((l) => l.length) ?? [0]));

  it('keeps one line at the preferred size when it fits, in a 16px lane', () => {
    expect(plan('Erbil', 3)).toEqual({ lines: ['Erbil'], size: 12, width: 16 });
    expect(plan('Annual review meeting', 11)).toMatchObject({ size: 12, width: 16 });
    expect(plan('Annual review meeting', 11)?.lines).toEqual(['Annual review meeting']);
  });

  it('wraps at word boundaries into the fewest lines that fit at the preferred size', () => {
    const two = plan('Annual review meeting', 7);
    expect(two?.lines).toEqual(['Annual review', 'meeting']);
    expect(two).toMatchObject({ size: 12, width: verticalLaneWidth(12, 16, 2) });
    expect(two?.width).toBe(30);
    const three = plan('Quarterly stakeholder alignment', 6);
    expect(three?.lines).toEqual(['Quarterly', 'stakeholder', 'alignment']);
    expect(three).toMatchObject({ size: 12, width: 44 });
  });

  it('never breaks a word and only ever rejoins the original words', () => {
    for (let d = 3; d < 16; d += 1) {
      const p = plan('Quarterly stakeholder alignment', d);
      if (p) expect(p.lines.join(' ')).toBe('Quarterly stakeholder alignment');
    }
  });

  it('keeps three lines and shrinks when even three lines do not fit at the preferred size', () => {
    const p = plan('Quarterly stakeholder alignment', 5);
    expect(p?.lines).toEqual(['Quarterly', 'stakeholder', 'alignment']);
    expect(p?.size).toBeGreaterThanOrEqual(9);
    expect(p?.size).toBeLessThan(12);
    // The longest line ('stakeholder') fits the 73px height at the shrunk size.
    expect(11 * 0.62 * 1.03 * (p?.size ?? 99)).toBeLessThanOrEqual(73);
    expect(p?.width).toBe(Math.ceil(1.15 * (p?.size ?? 0) * 3) + 2);
  });

  it('balances the lines so the longest one is as short as possible', () => {
    const p = plan('aa bbbbbbbb cc dddddd', 3);
    expect(p).toBeNull();
    const q = verticalPlan('aa bbbbbbbb cc dddddd', 4, 17, fonts, 12);
    // Of the three-line splits, "aa" / "bbbbbbbb" / "cc dddddd" has the shortest longest line (9).
    expect(q).not.toBeNull();
    expect(Math.max(...(q?.lines.map((l) => l.length) ?? [99]))).toBe(9);
  });

  it('falls back to horizontal (null) when three lines do not fit even at the minimum size', () => {
    expect(plan('Quarterly stakeholder alignment', 4)).toBeNull();
    expect(plan('Quarterly stakeholder alignment', 3)).toBeNull();
    expect(longest('Quarterly stakeholder alignment', 5)).toBe(11);
  });

  it('never breaks a single long word: it shrinks, then falls back to horizontal', () => {
    const word = 'Supercalifragilisticexpialidocious';
    expect(plan(word, 8)).toBeNull();
    const p = plan(word, 14);
    expect(p?.lines).toEqual([word]);
    expect(p?.size).toBeGreaterThanOrEqual(9);
    expect(p?.size).toBeLessThan(12);
  });

  it('is deterministic per row height: taller rows need fewer days', () => {
    const title = 'Quarterly stakeholder alignment workshop';
    const need = (rowHeight: number) => {
      for (let d = 1; d < 80; d += 1) {
        if (verticalPlan(title, d, rowHeight, fonts)) return d;
      }
      return Infinity;
    };
    expect(need(34)).toBeLessThan(need(17));
    expect(need(17)).toBe(need(17));
  });

  it('scales the preferred and minimum size with the root font size (text size setting)', () => {
    expect(plan('Lisbon conference', 8)).not.toBeNull();
    expect(plan('Lisbon conference', 8, { ...fonts, rem: 40 })).toBeNull();
  });

  it('wraps for a larger preferred size too (P=24)', () => {
    const p = plan('Quarterly stakeholder alignment', 14, fonts, 24);
    expect(p?.lines.length).toBeGreaterThan(1);
    expect(p?.size).toBeLessThanOrEqual(24);
  });
});

describe('rotated lane width follows the vertical text size', () => {
  it('is ceil(1.15 x size) + 2 px, and 16px at the default 12px', () => {
    expect(verticalLaneWidth(12)).toBe(16);
    expect(verticalLaneWidth(24)).toBe(30);
    expect(verticalLaneWidth(32)).toBe(39);
    expect(measurerFor(DEFAULT_FIT_FONTS).lane).toBe(16);
    expect(measurerFor(DEFAULT_FIT_FONTS, 16, 24).lane).toBe(30);
  });

  it('scales with the root font size like the text itself', () => {
    expect(measurerFor({ ...DEFAULT_FIT_FONTS, rem: 20 }, 16, 12).lane).toBe(
      Math.ceil(1.15 * 12 * (20 / 16)) + 2,
    );
  });

  it('reports the lane width in the month tracks', () => {
    const m = { ...measure, lane: verticalLaneWidth(24) };
    const layout = march([vertical('a', day(2), day(9))], 2, m);
    expect(monthTracks(layout, none, m).lane).toBe(30);
  });
});

describe('rotated lane width follows the number of lines', () => {
  it('is ceil(1.15 x size x lines) + 2 px', () => {
    expect(verticalLaneWidth(12, 16, 1)).toBe(16);
    expect(verticalLaneWidth(12, 16, 2)).toBe(30);
    expect(verticalLaneWidth(12, 16, 3)).toBe(44);
    expect(verticalLaneWidth(10, 16, 3)).toBe(Math.ceil(1.15 * 10 * 3) + 2);
  });

  // 'wrapped' names (more than 8 characters) need two lines and a 30px column.
  const wrapping: TextMeasurer = {
    ...measure,
    plan: (title) =>
      title.length > 8
        ? { lines: [title.slice(0, 4), title.slice(4)], size: 12, width: 30 }
        : { lines: [title], size: 12, width: 16 },
  };

  it('sizes each rotated lane to the widest label it holds', () => {
    const layout = march(
      [vertical('short', day(10), day(14)), vertical('a longer name', day(10), day(14))],
      4,
      wrapping,
    );
    const t = monthTracks(layout, none, wrapping);
    // 'a longer name' sorts first (same span, title order) and takes lane 0.
    expect(t.lanes).toEqual([30, 16]);
    expect(t.days[9]).toMatchObject({ rotated: 2, rotatedWidth: 46 });
    expect(t.width).toBe(46);
    expect(t.labels['a longer name:10']).toMatchObject({ width: 30 });
    expect(t.labels['short:10']).toMatchObject({ width: 16 });
  });

  it('makes a shared lane as wide as its widest label for the whole month', () => {
    const layout = march(
      [vertical('short', day(2), day(4)), vertical('a longer name', day(5), day(8))],
      4,
      wrapping,
    );
    const t = monthTracks(layout, none, wrapping);
    expect(t.lanes).toEqual([30]);
    expect(t.days[2]?.rotatedWidth).toBe(30);
  });

  it('keeps 16px lanes when every name fits on one line', () => {
    const layout = march([vertical('short', day(10), day(14))], 4, wrapping);
    const t = monthTracks(layout, none, wrapping);
    expect(t.lanes).toEqual([16]);
    expect(t.width).toBe(16);
  });
});
