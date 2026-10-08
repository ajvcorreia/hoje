import { describe, expect, it } from 'vitest';
import { monthFitWidth, monthVerticalWidth, type TextMeasurer } from './fitWidth';
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

describe('monthFitWidth', () => {
  it('needs the title of a single-day event plus padding and slack', () => {
    expect(monthFitWidth(march([ev('lunch', '2026-03-10', '2026-03-10')]), none, measure)).toBe(
      5 * 6 + 8 + 4,
    );
  });

  it('needs nothing in a month without text', () => {
    expect(monthFitWidth(march([]), none, measure)).toBe(0);
  });

  it('ignores the title of a vertically labelled block while names are rotated', () => {
    const layout = march([ev('conference', '2026-03-10', '2026-03-12', { labelVertical: true })]);
    expect(monthFitWidth(layout, none, measure)).toBe(0);
  });

  it('counts a vertical title as horizontal text when names are not rotated', () => {
    const layout = march(
      [ev('conference', '2026-03-10', '2026-03-12', { labelVertical: true })],
      4,
    );
    expect(monthFitWidth(layout, none, measure, 0)).toBe(10 * 6 + 8 + 4);
  });

  it('still needs the title of a multi-day event that is not rotated', () => {
    const layout = march([ev('trip', '2026-03-10', '2026-03-12')]);
    expect(monthFitWidth(layout, none, measure)).toBe(4 * 6 + 8 + 4);
  });

  it('needs the holiday name on an empty day', () => {
    expect(monthFitWidth(march([]), new Map([[5, 'Holiday']]), measure)).toBe(7 * 6 + 8 + 4);
  });
});

describe('monthVerticalWidth', () => {
  const vertical = (key: string, start: string, end: string) =>
    ev(key, start, end, { labelVertical: true });

  it('is 0 without a rotated label', () => {
    expect(monthVerticalWidth(march([ev('trip', '2026-03-10', '2026-03-12')]), 2)).toBe(0);
    expect(monthVerticalWidth(march([]), 2)).toBe(0);
  });

  it('is 0 when names are never rotated', () => {
    expect(monthVerticalWidth(march([vertical('a', '2026-03-10', '2026-03-12')], 4), 0)).toBe(0);
  });

  it('is one lane for a label that has its days to itself', () => {
    const w = monthVerticalWidth(march([vertical('a', '2026-03-10', '2026-03-12')]), 2);
    expect(w).toBeGreaterThan(0);
    expect(monthVerticalWidth(march([vertical('a', '2026-03-10', '2026-03-12')]), 1)).toBe(w);
  });

  it('is a lane per column when the label shares a day with another event', () => {
    const one = monthVerticalWidth(march([vertical('a', '2026-03-10', '2026-03-12')]), 2);
    const shared = march([
      vertical('a', '2026-03-10', '2026-03-12'),
      ev('lunch', '2026-03-12', '2026-03-12'),
    ]);
    expect(monthVerticalWidth(shared, 2)).toBe(2 * one);
  });

  it('is much narrower than the horizontal minimum for a long title', () => {
    const layout = march([vertical('A very long conference name', '2026-03-10', '2026-03-12')]);
    expect(monthFitWidth(layout, none, measure)).toBe(0);
    expect(monthVerticalWidth(layout, 2)).toBeLessThan(60);
  });
});
