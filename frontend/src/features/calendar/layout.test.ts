import { describe, expect, it } from 'vitest';
import { daysInMonth, firstDayRow } from '../../lib/dates';
import {
  GRID_ROWS,
  compareForLayout,
  layoutMonth,
  moveFocusDate,
  rowOfDay,
  rowsUsed,
  type Placed,
  type LayoutInput,
} from './layout';

const ev = (
  key: string,
  start: string,
  end: string,
  extra: Partial<LayoutInput> = {},
): LayoutInput => ({ key, start, end, allDay: true, title: key, ...extra });

describe('weekday rows', () => {
  it('puts day 1 on its weekday row (Monday first)', () => {
    expect(firstDayRow(2026, 0)).toBe(3); // Thu 1 Jan 2026
    expect(firstDayRow(2026, 1)).toBe(6); // Sun 1 Feb 2026
    expect(firstDayRow(2026, 5)).toBe(0); // Mon 1 Jun 2026
    expect(firstDayRow(2024, 1)).toBe(3); // Thu 1 Feb 2024 (leap year)
    expect(daysInMonth(2024, 1)).toBe(29);
    expect(rowsUsed(2024, 1)).toBe(32);
    expect(rowOfDay(3, 1)).toBe(3);
    expect(rowOfDay(3, 29)).toBe(31);
  });

  it('never needs more than 37 rows, and reaches 37 in the worst case', () => {
    for (let year = 2000; year <= 2100; year += 1) {
      for (let month = 0; month < 12; month += 1) {
        expect(rowsUsed(year, month)).toBeLessThanOrEqual(GRID_ROWS);
      }
    }
    // Sun 1 Aug 2027 is a 31-day month starting on the last weekday row: 6 + 31.
    expect(rowsUsed(2027, 7)).toBe(GRID_ROWS);
  });
});

describe('compareForLayout', () => {
  it('orders multi-day by start then longer first, then single all-day, then timed', () => {
    const items = [
      ev('timed-late', '2026-03-05', '2026-03-05', { allDay: false, startTime: '15:00' }),
      ev('timed-early', '2026-03-05', '2026-03-05', { allDay: false, startTime: '08:00' }),
      ev('single-b', '2026-03-05', '2026-03-05'),
      ev('single-a', '2026-03-05', '2026-03-05'),
      ev('short', '2026-03-02', '2026-03-03'),
      ev('long', '2026-03-02', '2026-03-09'),
      ev('earlier', '2026-03-01', '2026-03-02'),
    ];
    expect([...items].sort(compareForLayout).map((e) => e.key)).toEqual([
      'earlier',
      'long',
      'short',
      'single-a',
      'single-b',
      'timed-early',
      'timed-late',
    ]);
  });
});

const keys = (list: readonly (Placed | null | undefined)[]) =>
  list.map((p) => p?.input.key ?? null);

describe('layoutMonth', () => {
  it('lays a single event over every day of its span with no overflow', () => {
    const days = layoutMonth([ev('a', '2026-03-10', '2026-03-12')], 2026, 2);
    expect(days).toHaveLength(31);
    for (const d of [10, 11, 12]) {
      expect(days[d - 1]?.total).toBe(1);
      expect(keys(days[d - 1]?.items ?? [])).toEqual(['a']);
      expect(days[d - 1]?.rotated).toEqual([]);
    }
    expect(days[8]?.total).toBe(0);
    expect(days[9]?.items[0]).toMatchObject({ showTitle: true, joinPrev: false, joinNext: true });
    expect(days[10]?.items[0]).toMatchObject({ showTitle: false, joinPrev: true, joinNext: true });
    expect(days[11]?.items[0]).toMatchObject({ showTitle: false, joinPrev: true, joinNext: false });
  });

  it('packs the events of a day left to right in placement order, multi-day first', () => {
    const days = layoutMonth(
      [ev('lunch', '2026-03-12', '2026-03-12'), ev('trip', '2026-03-10', '2026-03-14')],
      2026,
      2,
    );
    expect(keys(days[11]?.items ?? [])).toEqual(['trip', 'lunch']);
    expect(keys(days[9]?.items ?? [])).toEqual(['trip']);
    expect(days[11]?.total).toBe(2);
    expect(days[11]?.overflow).toBe(0);
  });

  it('leaves no gap: a multi-day event moves left when the event before it ends', () => {
    const days = layoutMonth(
      [
        ev('a', '2026-03-10', '2026-03-10'),
        ev('b', '2026-03-09', '2026-03-12'),
        ev('c', '2026-03-10', '2026-03-10'),
      ],
      2026,
      2,
      6,
    );
    expect(keys(days[9]?.items ?? [])).toEqual(['b', 'a', 'c']);
    expect(keys(days[10]?.items ?? [])).toEqual(['b']);
    expect(days[10]?.items[0]?.lane).toBe(0);
  });

  it('puts events that do not fit into the +N count only on the days they cover', () => {
    const days = layoutMonth(
      [
        ev('a', '2026-03-10', '2026-03-10'),
        ev('b', '2026-03-10', '2026-03-10'),
        ev('c', '2026-03-10', '2026-03-10'),
        ev('d', '2026-03-10', '2026-03-10'),
      ],
      2026,
      2,
    );
    expect(days[9]?.total).toBe(4);
    expect(days[9]?.overflow).toBe(2);
    expect(keys(days[9]?.items ?? [])).toEqual(['a', 'b']);
    expect(days[8]?.overflow).toBe(0);
  });

  it('counts one extra event as +1 next to two placed ones', () => {
    const days = layoutMonth(
      [
        ev('a', '2026-03-10', '2026-03-10'),
        ev('b', '2026-03-10', '2026-03-10'),
        ev('c', '2026-03-10', '2026-03-10'),
      ],
      2026,
      2,
    );
    expect(days[9]?.overflow).toBe(1);
  });

  it('continues a block into the next month column with the title repeated', () => {
    const trip = ev('trip', '2026-01-30', '2026-02-02');
    const jan = layoutMonth([trip], 2026, 0);
    const feb = layoutMonth([trip], 2026, 1);
    expect(jan[29]?.items[0]).toMatchObject({ showTitle: true, joinPrev: false, joinNext: true });
    expect(jan[30]?.items[0]).toMatchObject({ showTitle: false, joinPrev: true, joinNext: false });
    expect(feb[0]?.items[0]).toMatchObject({ showTitle: true, joinPrev: false, joinNext: true });
    expect(feb[1]?.items[0]).toMatchObject({ showTitle: false, joinPrev: true, joinNext: false });
    expect(feb[2]?.total).toBe(0);
  });

  it('shows at most laneCount events per day and counts the rest as overflow', () => {
    const four = ['a', 'b', 'c', 'd'].map((k) => ev(k, '2026-03-10', '2026-03-10'));
    const one = layoutMonth(four, 2026, 2, 1);
    expect(one[9]?.items).toHaveLength(1);
    expect(one[9]?.overflow).toBe(3);
    const six = layoutMonth([...four, ev('e', '2026-03-10', '2026-03-10')], 2026, 2, 6);
    expect(keys(six[9]?.items ?? [])).toEqual(['a', 'b', 'c', 'd', 'e']);
    expect(six[9]?.overflow).toBe(0);
    expect(layoutMonth(four, 2026, 2, 3)[9]?.overflow).toBe(1);
  });

  it('ignores events outside the month', () => {
    const days = layoutMonth([ev('x', '2026-04-01', '2026-04-05')], 2026, 2);
    expect(days.every((d) => d.total === 0)).toBe(true);
  });
});

describe('layoutMonth with rotated blocks', () => {
  const rotates = (input: LayoutInput) => !!input.labelVertical;
  const vertical = (key: string, start: string, end: string) =>
    ev(key, start, end, { labelVertical: true });

  it('puts a rotated block in a lane of its own, outside the packed events', () => {
    const days = layoutMonth(
      [
        ev('flight', '2026-03-10', '2026-03-10'),
        vertical('doha', '2026-03-10', '2026-03-16'),
        ev('pay', '2026-03-15', '2026-03-15'),
      ],
      2026,
      2,
      2,
      rotates,
    );
    for (let d = 10; d <= 16; d += 1) expect(days[d - 1]?.rotated[0]?.input.key).toBe('doha');
    expect(days[9]?.rotated[0]).toMatchObject({
      rotated: true,
      lane: 0,
      blockLen: 7,
      showTitle: true,
    });
    expect(keys(days[9]?.items ?? [])).toEqual(['flight']);
    // No empty slot ahead of the event on day 15 either.
    expect(keys(days[14]?.items ?? [])).toEqual(['pay']);
    expect(days[14]?.items[0]?.lane).toBe(0);
  });

  it('shares a lane between blocks that do not overlap, separates overlapping ones', () => {
    const days = layoutMonth(
      [
        vertical('a', '2026-03-02', '2026-03-04'),
        vertical('b', '2026-03-05', '2026-03-07'),
        vertical('c', '2026-03-06', '2026-03-09'),
      ],
      2026,
      2,
      4,
      rotates,
    );
    expect(days[2]?.rotated).toHaveLength(2);
    expect(keys(days[2]?.rotated ?? [])).toEqual(['a', null]);
    expect(keys(days[4]?.rotated ?? [])).toEqual(['b', null]);
    expect(keys(days[5]?.rotated ?? [])).toEqual(['b', 'c']);
    expect(keys(days[8]?.rotated ?? [])).toEqual([null, 'c']);
  });

  it('does not rotate what the predicate refuses, nor a single day of the month', () => {
    const refused = layoutMonth(
      [vertical('a', '2026-03-10', '2026-03-12')],
      2026,
      2,
      2,
      () => false,
    );
    expect(refused[9]?.rotated).toEqual([]);
    expect(keys(refused[9]?.items ?? [])).toEqual(['a']);
    const clipped = layoutMonth([vertical('b', '2026-03-31', '2026-04-03')], 2026, 2, 2, rotates);
    expect(clipped[30]?.rotated).toEqual([]);
    expect(keys(clipped[30]?.items ?? [])).toEqual(['b']);
  });

  it('asks the predicate with the number of days inside the month', () => {
    const seen: number[] = [];
    layoutMonth([vertical('b', '2026-03-30', '2026-04-03')], 2026, 2, 2, (_, days) => {
      seen.push(days);
      return false;
    });
    expect(seen).toEqual([2]);
  });

  it('counts rotated and horizontal events together against the per-day maximum', () => {
    const days = layoutMonth(
      [
        vertical('v1', '2026-03-10', '2026-03-12'),
        vertical('v2', '2026-03-10', '2026-03-12'),
        ev('x', '2026-03-11', '2026-03-11'),
        ev('y', '2026-03-11', '2026-03-11'),
      ],
      2026,
      2,
      3,
      rotates,
    );
    expect(keys(days[10]?.rotated ?? [])).toEqual(['v1', 'v2']);
    expect(keys(days[10]?.items ?? [])).toEqual(['x']);
    expect(days[10]?.overflow).toBe(1);
    expect(days[10]?.total).toBe(4);
  });

  it('gives rotated blocks priority over earlier horizontal events', () => {
    const days = layoutMonth(
      [ev('h', '2026-03-05', '2026-03-12'), vertical('v', '2026-03-10', '2026-03-12')],
      2026,
      2,
      1,
      rotates,
    );
    expect(keys(days[10]?.rotated ?? [])).toEqual(['v']);
    expect(days[10]?.items).toEqual([]);
    expect(days[10]?.overflow).toBe(1);
    expect(keys(days[5]?.items ?? [])).toEqual(['h']);
  });

  it('overflows a rotated block as a whole when a day of its span is full', () => {
    const days = layoutMonth(
      [vertical('v1', '2026-03-10', '2026-03-12'), vertical('v2', '2026-03-12', '2026-03-14')],
      2026,
      2,
      1,
      rotates,
    );
    expect(keys(days[9]?.rotated ?? [])).toEqual(['v1']);
    expect(days[12]?.rotated).toEqual([null]);
    expect(days[12]?.overflow).toBe(1);
    expect(days[11]?.overflow).toBe(1);
  });
});

describe('moveFocusDate', () => {
  it('moves by day inside a month and clamps at the edges', () => {
    expect(moveFocusDate('2026-03-10', 'ArrowDown')).toBe('2026-03-11');
    expect(moveFocusDate('2026-03-10', 'ArrowUp')).toBe('2026-03-09');
    expect(moveFocusDate('2026-03-01', 'ArrowUp')).toBe('2026-03-01');
    expect(moveFocusDate('2026-03-31', 'ArrowDown')).toBe('2026-03-31');
  });

  it('moves to the same weekday row in the neighbouring month', () => {
    // Thu 1 Jan 2026 is row 3; Feb starts on row 6, so row 3 is empty -> clamps to day 1.
    expect(moveFocusDate('2026-01-01', 'ArrowRight')).toBe('2026-02-01');
    // Mon 5 Jan 2026 is row 7; in Feb that is day 2 (Mon 2 Feb).
    expect(moveFocusDate('2026-01-05', 'ArrowRight')).toBe('2026-02-02');
    expect(moveFocusDate('2026-02-02', 'ArrowLeft')).toBe('2026-01-05');
    expect(moveFocusDate('2026-01-05', 'ArrowLeft')).toBe('2026-01-05');
  });
});
