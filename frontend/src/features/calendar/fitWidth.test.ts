import { describe, expect, it } from 'vitest';
import { monthTracks, type TextMeasurer } from './fitWidth';
import { layoutMonth, type LayoutInput } from './layout';

// 6px per character, no canvas needed.
const measure: TextMeasurer = {
  text: (v) => v.length * 6,
  italic: (v) => v.length * 6,
  chip: (v) => v.length * 5,
};

const ev = (
  key: string,
  start: string,
  end: string,
  extra: Partial<LayoutInput> = {},
): LayoutInput => ({ key, start, end, allDay: true, title: key, ...extra });

const march = (inputs: LayoutInput[], maxEvents = 2) => layoutMonth(inputs, 2026, 2, maxEvents);
const none = new Map<number, string>();
const day = (d: number) => `2026-03-${String(d).padStart(2, '0')}`;
const vertical = (key: string, start: string, end: string) =>
  ev(key, start, end, { labelVertical: true });

describe('monthTracks', () => {
  it('needs the title of a single event plus padding and slack, using the whole cell', () => {
    const t = monthTracks(march([ev('lunch', day(10), day(10))]), none, measure);
    expect(t.width).toBe(5 * 6 + 8 + 4);
    expect(t.lanes).toEqual([]);
    expect(t.onlyVertical).toBe(false);
  });

  it('needs nothing in a month without text', () => {
    expect(monthTracks(march([]), none, measure)).toMatchObject({ width: 0, onlyVertical: false });
  });

  it('puts the events of a day side by side: one track per lane', () => {
    const t = monthTracks(
      march([ev('alpha', day(10), day(10)), ev('be', day(10), day(10))]),
      none,
      measure,
    );
    expect(t.lanes).toEqual([5 * 6 + 8, 2 * 6 + 8]);
    expect(t.width).toBe(5 * 6 + 8 + (2 * 6 + 8) + 4);
  });

  it('aligns lanes: each lane is as wide as its widest title in the month', () => {
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
    expect(t.lanes).toEqual([6 * 6 + 8, 2 * 6 + 8]);
  });

  it('adds the overlay text before the lanes on a day with events', () => {
    const t = monthTracks(march([ev('lunch', day(5), day(5))]), new Map([[5, 'Holiday']]), measure);
    expect(t.overlay).toBe(7 * 6 + 8);
    expect(t.lanes).toEqual([5 * 6 + 8]);
    expect(t.width).toBe(7 * 6 + 8 + 5 * 6 + 8 + 4);
  });

  it('needs only the overlay text on an empty day', () => {
    const t = monthTracks(march([]), new Map([[5, 'Holiday']]), measure);
    expect(t.width).toBe(7 * 6 + 8 + 4);
    expect(t.overlay).toBe(0);
  });

  it('adds a chip track when a day overflows', () => {
    const three = ['aa', 'bb', 'cc'].map((k) => ev(k, day(10), day(10)));
    const t = monthTracks(march(three), none, measure);
    expect(t.chip).toBe(2 * 5 + 12);
    expect(t.width).toBe(2 * (2 * 6 + 8) + (2 * 5 + 12) + 4);
  });

  it('works for up to six lanes', () => {
    const six = ['a', 'b', 'c', 'd', 'e', 'f'].map((k) => ev(k, day(10), day(10)));
    const t = monthTracks(march(six, 6), none, measure);
    expect(t.lanes).toHaveLength(6);
    expect(t.chip).toBe(0);
  });

  it('still needs the title of a multi-day event that is not rotated', () => {
    expect(monthTracks(march([ev('trip', day(10), day(12))]), none, measure).width).toBe(
      4 * 6 + 8 + 4,
    );
  });
});

describe('monthTracks with rotated labels', () => {
  it('needs one lane width for a label that has its days to itself, not its text width', () => {
    const t = monthTracks(march([vertical('conference', day(10), day(12))]), none, measure);
    expect(t.width).toBe(16);
    expect(t.onlyVertical).toBe(true);
  });

  it('is the same for any title length', () => {
    const t = monthTracks(
      march([vertical('A very long conference name', day(10), day(12))]),
      none,
      measure,
    );
    expect(t.width).toBe(16);
  });

  it('gives each lane that carries a rotated label a lane width, whatever the max events', () => {
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
    expect(t.lanes).toEqual([16, 16, 16]);
    expect(t.width).toBe(48);
    expect(t.onlyVertical).toBe(true);
  });

  it('adds a lane next to horizontal text when a label shares days with another event', () => {
    const t = monthTracks(
      march([vertical('a', day(10), day(12)), ev('lunch', day(12), day(12))]),
      none,
      measure,
    );
    expect(t.lanes).toEqual([16, 5 * 6 + 8]);
    expect(t.width).toBe(16 + 5 * 6 + 8 + 4);
    expect(t.onlyVertical).toBe(false);
  });
});
