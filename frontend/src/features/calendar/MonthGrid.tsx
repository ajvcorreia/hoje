import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type FocusEvent,
  type MouseEvent,
  type WheelEvent,
} from 'react';
import { getISOWeek } from 'date-fns';
import type { Category, Occurrence } from '../../api/types';
import {
  WEEKDAY_LETTERS,
  daysInMonth,
  firstDayRow,
  formatDayHeading,
  monthName,
} from '../../lib/dates';
import { useWeekNumbers } from '../../lib/weekNumbers';
import { toLayoutInput } from '../events/occurrences';
import {
  GRID_ROWS,
  layoutMonth,
  moveFocusDate,
  type ArrowKey,
  type DayLayout,
  type LayoutInput,
} from './layout';

/** Height of the sticky month header row, px. */
export const HEAD_HEIGHT = 28;
/** Below this row height the grid stops squeezing and scrolls vertically instead. */
export const MIN_ROW_HEIGHT = 16;
const WEEK_START = 1; // Monday
const ARROWS = new Set<string>(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);

export interface ScrollRequest {
  /** 0-based month to bring into view. */
  month: number;
  /** Change to re-trigger scrolling to the same month. */
  nonce: number;
}

interface MonthGridProps {
  year: number;
  /** Occurrences of the year, already filtered for hidden categories. */
  occurrences: Occurrence[];
  categories: Category[];
  /** ISO weekday numbers shaded as weekend rows. */
  weekendDays: number[];
  /** Today as `yyyy-MM-dd`. */
  today: string;
  /** A day cell was activated (click, Enter or Space). */
  onOpenDay(date: string, anchor: HTMLElement): void;
  scrollRequest: ScrollRequest | null;
}

interface MonthColumnProps {
  year: number;
  month: number;
  inputs: LayoutInput[];
  weekendDays: number[];
  today: string;
  /** Day (1-based) holding the roving tabindex in this column, or 0. */
  tabDay: number;
  /** Show the ISO week-number sub-column. */
  weeks: boolean;
}

const pad = (n: number) => String(n).padStart(2, '0');

const MonthColumn = memo(function MonthColumn({
  year,
  month,
  inputs,
  weekendDays,
  today,
  tabDay,
  weeks,
}: MonthColumnProps) {
  const layout = useMemo(() => layoutMonth(inputs, year, month), [inputs, year, month]);
  const offset = firstDayRow(year, month, WEEK_START);
  const dim = daysInMonth(year, month);
  const prefix = `${String(year).padStart(4, '0')}-${pad(month + 1)}-`;
  const isCurrentMonth = today.startsWith(prefix);
  const title = `${monthName(month)} ${year}`;

  // One rotated label per block segment of 2+ days whose event asks for a vertical name.
  const segments: {
    key: string;
    title: string;
    colour?: string;
    row: number;
    len: number;
    lane: number;
    split: boolean;
  }[] = [];
  const verticalStarts = new Set<string>();
  for (let day = 1; day <= dim; day += 1) {
    const d = layout[day - 1] as DayLayout;
    for (const p of d.lanes) {
      if (!p || !p.showTitle || !p.joinNext || !p.input.labelVertical) continue;
      let len = 1;
      let split = d.total > 1;
      for (;;) {
        const next = layout[day - 1 + len];
        const q = next?.lanes[p.lane];
        if (!next || !q || q.input.key !== p.input.key || !q.joinPrev) break;
        if (next.total > 1) split = true;
        len += 1;
      }
      verticalStarts.add(`${day}:${p.lane}`);
      segments.push({
        key: `${p.input.key}:${day}`,
        title: p.input.title,
        colour: p.input.colour,
        row: day - 1 + offset,
        len,
        lane: p.lane,
        split,
      });
    }
  }

  // Week segments: rows are Monday-aligned, so a week is a contiguous run of rows.
  const weekCells = [];
  if (weeks) {
    for (let day = 1; day <= dim;) {
      const row = day - 1 + offset;
      const len = Math.min(7 - (row % 7), dim - day + 1);
      weekCells.push(
        <div
          key={`w${day}`}
          className="cal-wk"
          data-week={getISOWeek(new Date(year, month, day))}
          title={`Week ${getISOWeek(new Date(year, month, day))}`}
          style={{ gridRow: `${row + 2} / span ${len}` }}
        >
          {getISOWeek(new Date(year, month, day))}
        </div>,
      );
      day += len;
    }
  }

  const cells = [];
  for (let row = 0; row < GRID_ROWS; row += 1) {
    const day = row - offset + 1;
    const weekend = weekendDays.includes(((WEEK_START - 1 + row) % 7) + 1) || undefined;
    const gridRow = { gridRow: row + 2 };
    if (day < 1 || day > dim) {
      cells.push(
        <div
          key={row}
          className="cal-empty"
          data-row={row}
          data-weekend={weekend}
          style={gridRow}
        />,
      );
      continue;
    }
    const d = layout[day - 1] as DayLayout;
    const iso = `${prefix}${pad(day)}`;
    const isToday = iso === today;
    const placed = d.lanes.filter((l) => l !== null);
    const single = d.total === 1;
    const lead = single ? placed[0] : d.lanes[0];
    const label = `${formatDayHeading(iso)} ${year}${
      d.total > 0 ? `, ${d.total} ${d.total === 1 ? 'event' : 'events'}` : ''
    }`;
    cells.push(
      <button
        key={row}
        type="button"
        className="cal-cell"
        data-date={iso}
        data-row={row}
        data-weekend={weekend}
        data-today={isToday || undefined}
        data-cat={lead?.input.colour}
        tabIndex={day === tabDay ? 0 : -1}
        aria-label={label}
        style={gridRow}
      >
        <span className="cal-num" aria-hidden="true">
          {day}
        </span>
        {placed.map((p) => (
          <span
            key={p.lane}
            className="cal-ev"
            data-half={single ? undefined : ''}
            data-lane={single ? 'full' : String(p.lane)}
            data-cat={p.input.colour}
            data-join-next={p.joinNext || undefined}
          >
            {p.showTitle && !verticalStarts.has(`${day}:${p.lane}`) ? p.input.title : ''}
          </span>
        ))}
        {d.overflow > 0 ? <span className="cal-more">+{d.overflow}</span> : null}
      </button>,
    );
  }

  return (
    <div
      role="group"
      aria-label={title}
      className="cal-col"
      data-month={month}
      data-weeks={weeks || undefined}
    >
      <div className="cal-head" data-current={isCurrentMonth || undefined}>
        {monthName(month)}
      </div>
      {weekCells}
      {cells}
      {segments.map((seg) => (
        <span
          key={seg.key}
          className="cal-vlabel"
          aria-hidden="true"
          data-cat={seg.colour}
          data-lane={seg.split ? String(seg.lane) : 'full'}
          style={{ '--seg-row': seg.row, '--seg-len': seg.len } as CSSProperties}
        >
          <span className="cal-vlabel-text">{seg.title}</span>
        </span>
      ))}
    </div>
  );
});

const GUTTER_ROWS = Array.from({ length: GRID_ROWS }, (_, row) => row);

/**
 * Desktop calendar: all 12 months of `year` side by side, rows aligned by weekday.
 *
 * Geometry: the scroll container is as tall as the space the page gives it. A
 * `ResizeObserver` turns that into `--row-h = (height - header) / 37`, so all 37 rows fit
 * without vertical scrolling; if that would be under {@link MIN_ROW_HEIGHT} the rows stay
 * at 16 px and the container scrolls vertically (headers and gutter are sticky). Columns
 * are `minmax(180px, 1fr)`, giving a horizontal scroll strip when narrow.
 *
 * Cells are plain buttons with a roving tabindex; arrow keys move between days.
 * Clicks, Enter and Space are delegated to a single handler (`onOpenDay`).
 */
export function MonthGrid({
  year,
  occurrences,
  categories,
  weekendDays,
  today,
  onOpenDay,
  scrollRequest,
}: MonthGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const [weeks] = useWeekNumbers();
  const [rowHeight, setRowHeight] = useState(MIN_ROW_HEIGHT);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      const next = Math.max(
        MIN_ROW_HEIGHT,
        Math.floor(((el.clientHeight - HEAD_HEIGHT) / GRID_ROWS) * 100) / 100,
      );
      setRowHeight((prev) => (prev === next ? prev : next));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Partition the year's occurrences into one stable array per month column.
  const inputsByMonth = useMemo(() => {
    const colourOf = new Map(categories.map((c) => [c.id, c.colour]));
    const buckets: LayoutInput[][] = Array.from({ length: 12 }, () => []);
    const prefix = `${String(year).padStart(4, '0')}-`;
    for (const o of occurrences) {
      const input = toLayoutInput(o, colourOf.get(o.event.category_id));
      const first =
        o.occurrence_start < `${prefix}01-01` ? 0 : Number(o.occurrence_start.slice(5, 7)) - 1;
      const last =
        o.occurrence_end > `${prefix}12-31` ? 11 : Number(o.occurrence_end.slice(5, 7)) - 1;
      for (let m = first; m <= last; m += 1) buckets[m]?.push(input);
    }
    return buckets;
  }, [occurrences, categories, year]);

  // Roving tabindex.
  const defaultFocus = today.startsWith(`${year}-`) ? today : `${year}-01-01`;
  const [focusDate, setFocusDate] = useState(defaultFocus);
  const activeFocus = focusDate.startsWith(`${year}-`) ? focusDate : defaultFocus;
  const pendingFocus = useRef<string | null>(null);

  useEffect(() => {
    if (pendingFocus.current !== activeFocus) return;
    pendingFocus.current = null;
    gridRef.current?.querySelector<HTMLElement>(`[data-date="${activeFocus}"]`)?.focus();
  }, [activeFocus]);

  // Scroll a month into view on request (initial position, Today, search result).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !scrollRequest) return;
    const column = gridRef.current?.querySelector<HTMLElement>(
      `[data-month="${scrollRequest.month}"]`,
    );
    if (column) el.scrollLeft = Math.max(0, column.offsetLeft - 32);
  }, [scrollRequest]);

  const onClick = useCallback(
    (event: MouseEvent) => {
      const cell = (event.target as HTMLElement).closest<HTMLElement>('[data-date]');
      if (cell?.dataset.date) onOpenDay(cell.dataset.date, cell);
    },
    [onOpenDay],
  );

  const onKeyDown = useCallback((event: KeyboardEvent) => {
    if (!ARROWS.has(event.key)) return;
    const cell = (event.target as HTMLElement).closest<HTMLElement>('[data-date]');
    if (!cell?.dataset.date) return;
    event.preventDefault();
    const next = moveFocusDate(cell.dataset.date, event.key as ArrowKey, WEEK_START);
    pendingFocus.current = next;
    setFocusDate(next);
    if (next === cell.dataset.date) pendingFocus.current = null;
  }, []);

  const onFocus = useCallback((event: FocusEvent) => {
    const date = (event.target as HTMLElement).dataset.date;
    if (date) setFocusDate(date);
  }, []);

  // The vertical wheel scrolls sideways when there is nothing to scroll vertically.
  const onWheel = useCallback((event: WheelEvent) => {
    const el = scrollRef.current;
    if (!el || event.shiftKey || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
    if (el.scrollHeight > el.clientHeight + 1) return;
    el.scrollLeft += event.deltaY;
  }, []);

  const style = {
    '--row-h': `${rowHeight}px`,
    '--head-h': `${HEAD_HEIGHT}px`,
  } as CSSProperties;

  const focusMonth = Number(activeFocus.slice(5, 7)) - 1;
  const focusDay = Number(activeFocus.slice(8, 10));

  return (
    // The wrapper only delegates pointer/keyboard events from the day buttons inside it.
    <div
      ref={scrollRef}
      role="presentation"
      className="cal-scroll min-h-0 flex-1"
      onClick={onClick}
      onKeyDown={onKeyDown}
      onFocus={onFocus}
      onWheel={onWheel}
    >
      <div
        ref={gridRef}
        role="group"
        aria-label={`Calendar ${year}`}
        className="cal-grid"
        style={style}
      >
        <div className="cal-gutter" aria-hidden="true">
          <div className="cal-head" />
          {GUTTER_ROWS.map((row) => (
            <div
              key={row}
              className="cal-wd"
              data-weekend={weekendDays.includes(((WEEK_START - 1 + row) % 7) + 1) || undefined}
            >
              {WEEKDAY_LETTERS[(WEEK_START - 1 + row) % 7]}
            </div>
          ))}
        </div>
        {inputsByMonth.map((inputs, month) => (
          <MonthColumn
            key={month}
            year={year}
            month={month}
            inputs={inputs}
            weekendDays={weekendDays}
            today={today}
            tabDay={month === focusMonth ? focusDay : 0}
            weeks={weeks}
          />
        ))}
      </div>
    </div>
  );
}
