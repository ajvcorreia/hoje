import { describe, expect, it } from 'vitest';
import { firstDayRow, isWeekend, monthMatrix, toIso } from './dates';

describe('dates', () => {
  it('finds the weekday row of day 1', () => {
    expect(firstDayRow(2026, 0)).toBe(3); // Thu
    expect(firstDayRow(2026, 5)).toBe(0); // Mon 1 Jun 2026
    expect(firstDayRow(2026, 1, 7)).toBe(0); // Sunday-first: Sun 1 Feb 2026
  });

  it('detects weekend days from ISO numbers', () => {
    expect(isWeekend('2026-01-03', [6, 7])).toBe(true);
    expect(isWeekend('2026-01-05', [6, 7])).toBe(false);
    expect(isWeekend(new Date(2026, 0, 4), [7])).toBe(true);
  });

  it('builds a Monday-first month matrix', () => {
    const weeks = monthMatrix(2026, 0);
    expect(weeks[0]).toEqual([
      null,
      null,
      null,
      '2026-01-01',
      '2026-01-02',
      '2026-01-03',
      '2026-01-04',
    ]);
    expect(weeks.every((w) => w.length === 7)).toBe(true);
    expect(weeks.flat().filter(Boolean)).toHaveLength(31);
    expect(toIso(new Date(2026, 0, 1))).toBe('2026-01-01');
  });
});
