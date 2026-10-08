import {
  Fragment,
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type FocusEvent,
  type MouseEvent,
  type PointerEvent,
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
import { useStrikePast } from '../../lib/strikePast';
import { useMaxEvents } from '../../lib/maxEvents';
import { useVerticalTextSize } from '../../lib/verticalTextSize';
import { toLayoutInput } from '../events/occurrences';
import {
  NO_HOLIDAYS,
  holidayText,
  isBirthday,
  isNonWorkingDay,
  overlayAria,
  type HolidayDay,
} from '../holidays/api';
import {
  DEFAULT_FIT_FONTS,
  clearMeasureCache,
  measurerFor,
  monthTracks,
  readFitFonts,
  rotationRule,
  type DayTracks,
  type FitFonts,
  type MonthTracks,
} from './fitWidth';
import { centerScrollLeft } from './centerScroll';
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
  /** Holidays of enabled calendars by date (empty when the Holidays chip is off). */
  holidays?: ReadonlyMap<string, HolidayDay[]>;
}

/** One month laid out for the current fonts and row height, with the geometry it needs. */
interface MonthFit {
  layout: DayLayout[];
  tracks: MonthTracks;
  /** Everything that affects rendering, so equal fits can be told apart cheaply. */
  key: string;
}

interface MonthColumnProps {
  year: number;
  month: number;
  /** The month's layout and day track widths (the widest day sets the column minimum). */
  fit: MonthFit;
  /** This month's holidays by date. */
  holidays: ReadonlyMap<string, HolidayDay[]>;
  /** Preferred font size (px) of rotated labels: sets `--vl-size`, the label shrinks only to fit. */
  verticalSize: number;
  weekendDays: number[];
  today: string;
  /** Day (1-based) holding the roving tabindex in this column, or 0. */
  tabDay: number;
  /** Show the ISO week-number sub-column. */
  weeks: boolean;
  /** Strike through days before `today`. */
  strikePast: boolean;
}

const pad = (n: number) => String(n).padStart(2, '0');
/** A track that is at least `width` px and takes spare space in proportion to it. */
const track = (width: number) => `minmax(${width}px, ${width}fr)`;

function MonthColumnImpl({
  year,
  month,
  fit,
  holidays,
  verticalSize,
  weekendDays,
  today,
  tabDay,
  weeks,
  strikePast,
}: MonthColumnProps) {
  const { layout, tracks } = fit;
  const offset = firstDayRow(year, month, WEEK_START);
  const dim = daysInMonth(year, month);
  const prefix = `${String(year).padStart(4, '0')}-${pad(month + 1)}-`;
  const isCurrentMonth = today.startsWith(prefix);
  const title = `${monthName(month)} ${year}`;

  // One rotated label per rotated block, drawn over its narrow column. The column index is the
  // block's rotated lane on every day it covers, so the label sits at the same x on all of them.
  const segments: {
    key: string;
    title: string;
    colour?: string;
    row: number;
    len: number;
    lane: number;
    past: boolean;
  }[] = [];
  for (let day = 1; day <= dim; day += 1) {
    for (const p of (layout[day - 1] as DayLayout).rotated) {
      if (!p || !p.showTitle) continue;
      segments.push({
        key: `${p.input.key}:${day}`,
        title: p.input.title,
        colour: p.input.colour,
        row: day - 1 + offset,
        len: p.blockLen,
        lane: p.lane,
        past: strikePast && `${prefix}${pad(day + p.blockLen - 1)}` < today,
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
    const t = tracks.days[day - 1] as DayTracks;
    const iso = `${prefix}${pad(day)}`;
    const isToday = iso === today;
    const dayHolidays = holidays.get(iso);
    const lead = d.rotated.find((p) => p) ?? d.items[0];
    const label = `${formatDayHeading(iso)} ${year}${
      d.total > 0 ? `, ${d.total} ${d.total === 1 ? 'event' : 'events'}` : ''
    }${dayHolidays ? `, ${overlayAria(dayHolidays)}` : ''}`;
    const onlyBirthdays = dayHolidays?.every(isBirthday) || undefined;
    // Day number | rotated columns | overlay | one track per event | chip. Columns are numbered
    // from 1 (the day number); every item names its own column, so a spacer column left by a
    // free rotated lane never shifts the others.
    const overlayCol = 2 + t.rotated;
    const firstItemCol = overlayCol + (t.overlay > 0 ? 1 : 0);
    const chipCol = firstItemCol + t.items.length;
    const template = [
      'var(--num-w)',
      ...Array.from({ length: t.rotated }, (_, l) => `${tracks.lanes[l] ?? tracks.lane}px`),
      ...(t.overlay > 0 ? [track(t.overlay)] : []),
      ...t.items.map(track),
      ...(t.chip > 0 ? [`${t.chip}px`] : []),
    ];
    // The last coloured box of a cell reaches the right edge: no separator border on it.
    const nothingAfterRotated = d.items.length === 0 && !dayHolidays && d.overflow === 0;
    const lastItem = d.overflow === 0 ? d.items.length - 1 : -1;
    cells.push(
      <button
        key={row}
        type="button"
        className="cal-cell"
        data-date={iso}
        data-row={row}
        data-weekend={weekend}
        data-holiday-off={isNonWorkingDay(dayHolidays) || undefined}
        data-today={isToday || undefined}
        data-past={(strikePast && iso < today) || undefined}
        data-cat={lead?.input.colour}
        tabIndex={day === tabDay ? 0 : -1}
        aria-label={label}
        style={
          template.length > 1 ? { ...gridRow, gridTemplateColumns: template.join(' ') } : gridRow
        }
      >
        <span className="cal-num" aria-hidden="true">
          {day}
        </span>
        {d.rotated.map((p, l) =>
          p ? (
            <span
              key={`r${l}`}
              className="cal-ev"
              data-rot={l}
              data-cat={p.input.colour}
              data-join-next={p.joinNext || undefined}
              data-edge={nothingAfterRotated && l === t.rotated - 1 ? '' : undefined}
              style={{ '--c': 2 + l } as CSSProperties}
            />
          ) : null,
        )}
        {dayHolidays ? (
          <span
            className="cal-hol"
            data-cat={dayHolidays[0]?.colour}
            data-holiday=""
            data-birthday={onlyBirthdays}
            style={{ '--c': overlayCol } as CSSProperties}
          >
            {holidayText(dayHolidays)}
          </span>
        ) : null}
        {d.items.map((p, i) => (
          <span
            key={p.lane}
            className="cal-ev"
            data-slot={i}
            data-cat={p.input.colour}
            data-join-next={p.joinNext || undefined}
            data-edge={i === lastItem ? '' : undefined}
            style={{ '--c': firstItemCol + i } as CSSProperties}
          >
            {p.showTitle ? p.input.title : ''}
          </span>
        ))}
        {d.overflow > 0 ? (
          <span className="cal-more" style={{ '--c': chipCol } as CSSProperties}>
            +{d.overflow}
          </span>
        ) : null}
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
      style={
        {
          '--m-start': offset,
          '--m-len': dim,
          '--col-fit': `${tracks.width}px`,
          '--vl-size': verticalSize,
        } as CSSProperties
      }
    >
      <div className="cal-head" data-current={isCurrentMonth || undefined}>
        {monthName(month)}
      </div>
      <span className="cal-month-outline" aria-hidden="true" />
      {weekCells}
      {cells}
      {segments.map((seg) => {
        const plan = tracks.labels[seg.key];
        const x = tracks.lanes.slice(0, seg.lane).reduce((a, w) => a + w, 0);
        return (
          <span
            key={seg.key}
            className="cal-vlabel"
            aria-hidden="true"
            data-cat={seg.colour}
            data-lane={seg.lane}
            data-lines={plan?.lines.length ?? 1}
            data-past={seg.past || undefined}
            style={
              {
                '--vl-x': `${x}px`,
                '--vl-w': `${tracks.lanes[seg.lane] ?? tracks.lane}px`,
                '--seg-row': seg.row,
                '--seg-len': seg.len,
                ...(plan ? { '--vl-fs': `${plan.size}px` } : null),
              } as CSSProperties
            }
          >
            <span className="cal-vlabel-text">
              {/* Whitespace between the line blocks (it renders nothing) keeps the text content equal
                  to the name. */}
              {(plan?.lines ?? [seg.title]).map((line, i) => (
                <Fragment key={i}>
                  {i > 0 ? ' ' : null}
                  <span className="cal-vline">{line}</span>
                </Fragment>
              ))}
            </span>
          </span>
        );
      })}
    </div>
  );
}

/**
 * Props are compared shallowly, except `fit`: a window resize recomputes every month's layout
 * (the row height feeds the rotated-label cutoff) but most months come out the same.
 */
function sameColumnProps(a: MonthColumnProps, b: MonthColumnProps): boolean {
  const keys = Object.keys(a) as (keyof MonthColumnProps)[];
  return keys.every((k) => (k === 'fit' ? a.fit.key === b.fit.key : Object.is(a[k], b[k])));
}

const MonthColumn = memo(MonthColumnImpl, sameColumnProps);

const SCROLL_KEYS = new Set(['ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown', 'Home', 'End']);

const GUTTER_ROWS = Array.from({ length: GRID_ROWS }, (_, row) => row);

/**
 * Desktop calendar: all 12 months of `year` side by side, rows aligned by weekday.
 *
 * Geometry: the scroll container is as tall as the space the page gives it. A
 * `ResizeObserver` turns that into `--row-h = (height - header) / 37`, so all 37 rows fit
 * without vertical scrolling; if that would be under {@link MIN_ROW_HEIGHT} the rows stay
 * at 16 px and the container scrolls vertically (headers and gutter are sticky). A day never grows
 * taller for its text: events, birthdays and holidays sit side by side in the row, and the month
 * column gets as wide as its widest day (see `monthTracks`), giving a horizontal scroll strip.
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
  holidays = NO_HOLIDAYS,
}: MonthGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const [weeks] = useWeekNumbers();
  const [strikePast] = useStrikePast();
  const [maxEvents] = useMaxEvents();
  const [verticalSize] = useVerticalTextSize();
  const [fonts, setFonts] = useState<FitFonts | null>(null);

  // Column widths follow the text: re-read the cell font on mount, on text-size changes and once web fonts load.
  useLayoutEffect(() => {
    const root = gridRef.current;
    // `reload`: web fonts finished loading, so widths measured earlier (with a fallback font)
    // are stale even though the font strings are unchanged; drop them and recompute.
    const refresh = (reload: boolean) => {
      if (reload) clearMeasureCache();
      const next = readFitFonts(root);
      setFonts((prev) =>
        !reload && prev && next && prev.normal === next.normal && prev.chip === next.chip
          ? prev
          : next && { ...next },
      );
    };
    const measure = () => refresh(false);
    const afterFonts = () => refresh(true);
    measure();
    const observer = new MutationObserver(measure);
    observer.observe(document.documentElement, { attributes: true });
    const fontSet = document.fonts as FontFaceSet | undefined;
    void fontSet?.ready.then(afterFonts);
    fontSet?.addEventListener?.('loadingdone', afterFonts);
    return () => {
      observer.disconnect();
      fontSet?.removeEventListener?.('loadingdone', afterFonts);
    };
  }, []);

  const holidaysByMonth = useMemo(() => {
    const buckets = Array.from({ length: 12 }, () => new Map<string, HolidayDay[]>());
    for (const [date, list] of holidays) {
      if (!date.startsWith(`${year}-`)) continue;
      buckets[Number(date.slice(5, 7)) - 1]?.set(date, list);
    }
    return buckets;
  }, [holidays, year]);
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

  // Required event-area width per month; memoised on the month inputs, holidays, font and row
  // height (a rotated label only fits a block tall enough for its name).
  const fits = useMemo(() => {
    const measure = measurerFor(fonts ?? DEFAULT_FIT_FONTS, rowHeight, verticalSize);
    const rotates = rotationRule(measure);
    return inputsByMonth.map((inputs, month): MonthFit => {
      const names = new Map<number, string>();
      for (const [date, list] of holidaysByMonth[month] ?? []) {
        names.set(Number(date.slice(8, 10)), holidayText(list));
      }
      const layout = layoutMonth(inputs, year, month, maxEvents, rotates);
      const tracks = monthTracks(layout, names, measure);
      return { layout, tracks, key: JSON.stringify([layout, tracks]) };
    });
  }, [fonts, rowHeight, inputsByMonth, holidaysByMonth, year, maxEvents, verticalSize]);

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

  // Centre a month column in the horizontal viewport (smooth unless reduced motion is requested).
  const centreMonth = useCallback((month: number, smooth: boolean) => {
    const el = scrollRef.current;
    const column = gridRef.current?.querySelector<HTMLElement>(`[data-month="${month}"]`);
    if (!el || !column) return;
    const left = centerScrollLeft(
      column.offsetLeft,
      column.offsetWidth,
      el.clientWidth,
      el.scrollWidth,
    );
    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (smooth && !reduced && typeof el.scrollTo === 'function') {
      el.scrollTo({ left, behavior: 'smooth' });
    } else {
      el.scrollLeft = left;
    }
  }, []);

  // Month last asked for, and whether the user has scrolled since: until they do, column widths
  // settling (fonts, measurement) re-centre it; afterwards the user's position is left alone.
  const requestedMonth = useRef<number | null>(null);
  const userScrolled = useRef(false);
  const markUserScrolled = useCallback(() => {
    userScrolled.current = true;
  }, []);

  // Scroll a month into view on request (initial position, Today, search result).
  useEffect(() => {
    if (!scrollRequest) return;
    userScrolled.current = false;
    requestedMonth.current = scrollRequest.month;
    centreMonth(scrollRequest.month, scrollRequest.nonce > 0);
  }, [scrollRequest, centreMonth]);

  useEffect(() => {
    const grid = gridRef.current;
    if (!grid || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      if (!userScrolled.current && requestedMonth.current !== null) {
        centreMonth(requestedMonth.current, false);
      }
    });
    observer.observe(grid);
    return () => observer.disconnect();
  }, [centreMonth]);

  // Highlight the weekday of the row under the pointer or keyboard focus. Written straight to a
  // DOM attribute (only when the row changes) so the 12 month columns never re-render for it.
  const hoverRow = useRef<string | null>(null);
  const setHoverRow = useCallback((row: string | null) => {
    if (hoverRow.current === row) return;
    hoverRow.current = row;
    const grid = gridRef.current;
    if (!grid) return;
    if (row === null) delete grid.dataset.hoverRow;
    else grid.dataset.hoverRow = row;
  }, []);
  const onPointerOver = useCallback(
    (event: PointerEvent) => {
      const row = (event.target as HTMLElement).closest('[data-row]');
      setHoverRow(row?.getAttribute('data-row') ?? null);
    },
    [setHoverRow],
  );
  const clearHoverRow = useCallback(() => setHoverRow(null), [setHoverRow]);

  const onClick = useCallback(
    (event: MouseEvent) => {
      const cell = (event.target as HTMLElement).closest<HTMLElement>('[data-date]');
      if (cell?.dataset.date) onOpenDay(cell.dataset.date, cell);
    },
    [onOpenDay],
  );

  const onKeyDown = useCallback((event: KeyboardEvent) => {
    if (SCROLL_KEYS.has(event.key)) userScrolled.current = true;
    if (!ARROWS.has(event.key)) return;
    const cell = (event.target as HTMLElement).closest<HTMLElement>('[data-date]');
    if (!cell?.dataset.date) return;
    event.preventDefault();
    const next = moveFocusDate(cell.dataset.date, event.key as ArrowKey, WEEK_START);
    pendingFocus.current = next;
    setFocusDate(next);
    if (next === cell.dataset.date) pendingFocus.current = null;
  }, []);

  const onFocus = useCallback(
    (event: FocusEvent) => {
      const target = event.target as HTMLElement;
      const date = target.dataset.date;
      if (date) {
        setFocusDate(date);
        setHoverRow(target.getAttribute('data-row'));
      }
    },
    [setHoverRow],
  );

  // The vertical wheel scrolls sideways when there is nothing to scroll vertically.
  const onWheel = useCallback((event: WheelEvent) => {
    userScrolled.current = true;
    const el = scrollRef.current;
    if (!el || event.shiftKey || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
    if (el.scrollHeight > el.clientHeight + 1) return;
    el.scrollLeft += event.deltaY;
  }, []);

  // Per-column minimum: lead (week + day-number columns and gaps) plus the widest text in that
  // month, or three day-number widths for a month without text. A month with nothing but
  // rotated labels needs just their lanes, not the horizontal-text minimum. Columns still share
  // spare width (1fr); the strip is as wide as the sum of the minimums and scrolls sideways.
  const lead = `var(--num-w) + ${weeks ? 'var(--wk-w-on)' : '0px'} + 2 * var(--gap)`;
  const columnMin = ({ tracks: { width, onlyVertical } }: MonthFit) => {
    const area = onlyVertical ? `${width}px` : `max(3 * var(--num-w), ${width}px)`;
    return `calc(${lead} + ${area})`;
  };
  const style = {
    '--row-h': `${rowHeight}px`,
    '--head-h': `${HEAD_HEIGHT}px`,
    gridTemplateColumns: `var(--gutter-w) ${fits.map((f) => `minmax(${columnMin(f)}, 1fr)`).join(' ')}`,
    width: `max(100%, calc(var(--gutter-w) + ${fits.map(columnMin).join(' + ')}))`,
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
      onPointerOver={onPointerOver}
      onPointerLeave={clearHoverRow}
      onBlur={clearHoverRow}
      onPointerDown={markUserScrolled}
      onTouchStart={markUserScrolled}
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
              data-row={row}
              data-weekend={weekendDays.includes(((WEEK_START - 1 + row) % 7) + 1) || undefined}
            >
              {WEEKDAY_LETTERS[(WEEK_START - 1 + row) % 7]}
            </div>
          ))}
        </div>
        {fits.map((fit, month) => (
          <MonthColumn
            key={month}
            year={year}
            month={month}
            fit={fit}
            holidays={holidaysByMonth[month] ?? NO_HOLIDAYS}
            verticalSize={verticalSize}
            weekendDays={weekendDays}
            today={today}
            tabDay={month === focusMonth ? focusDay : 0}
            weeks={weeks}
            strikePast={strikePast}
          />
        ))}
      </div>
    </div>
  );
}
