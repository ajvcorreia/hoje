import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearMeasureCache,
  monthTracks,
  rotationRule,
  verticalFits,
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
  fitsVertical: (title, days) => title.length <= days * 4,
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
    const fits = { ...measure, fitsVertical: () => true };
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

describe('verticalFits', () => {
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

  const daysNeeded = (title: string, rowHeight: number, f = fonts) => {
    for (let d = 1; d < 80; d += 1) if (verticalFits(title, d, rowHeight, f)) return d;
    return Infinity;
  };

  it('needs the name at the 9px minimum to fit the block height', () => {
    const long = 'Quarterly stakeholder alignment workshop';
    // (days * 17 - 12) / (em * 1.03) >= 9 with em = 0.62 * characters.
    expect(daysNeeded('Erbil', 17)).toBe(3);
    expect(daysNeeded(long, 17)).toBe(15);
    expect(verticalFits(long, 14, 17, fonts)).toBe(false);
    expect(verticalFits(long, 15, 17, fonts)).toBe(true);
  });

  it('is deterministic per row height: taller rows need fewer days', () => {
    const title = 'Quarterly stakeholder alignment workshop';
    expect(daysNeeded(title, 34)).toBeLessThan(daysNeeded(title, 17));
    expect(daysNeeded(title, 17)).toBe(daysNeeded(title, 17));
  });

  it('scales the minimum with the root font size (text size setting)', () => {
    expect(verticalFits('Lisbon conference', 8, 17, fonts)).toBe(true);
    expect(verticalFits('Lisbon conference', 8, 17, { ...fonts, rem: 40 })).toBe(false);
  });
});
