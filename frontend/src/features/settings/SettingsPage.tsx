import { useEffect } from 'react';
import { useLocation } from 'react-router';
import { THEMES, type Theme } from '../../lib/theme';
import { TEXT_SIZES, type TextSize } from '../../lib/textSize';
import { useWeekNumbers } from '../../lib/weekNumbers';
import {
  PAST_STRENGTHS,
  PAST_STYLES,
  isPastStrength,
  isPastStyle,
  usePastStrength,
  usePastStyle,
  useStrikePastSetting,
  type PastStrength,
  type PastStyle,
} from '../../lib/pastDays';
import {
  useIconsInCalendar,
  useIconsOnVertical,
  useShowCategoryIcons,
} from '../../lib/showCategoryIcons';
import { PILLS_POSITIONS, isPillsPosition, usePillsPosition } from '../../lib/pillsPosition';
import { MAX_PILLS_WIDTH, MIN_PILLS_WIDTH, usePillsWidth } from '../../lib/pillsWidth';
import { DEFAULT_PAST_STRIPE_COLOUR, usePastStripeColour } from '../../lib/pastStripeColour';
import {
  AUTO_TODO_MARKER_COLOUR,
  DEFAULT_TODO_MARKER_HEX,
  TODO_MARKERS,
  isTodoMarker,
  useTodoMarker,
  useTodoMarkerColour,
  type TodoMarker,
} from '../../lib/todoMarker';
import { isHex } from '../../styles/customColour';
import { MAX_MAX_EVENTS, MIN_MAX_EVENTS, useMaxEvents } from '../../lib/maxEvents';
import { useVerticalTextSize } from '../../lib/verticalTextSize';
import { useTheme } from '../../app/useTheme';
import { useTextSize } from '../../app/useTextSize';
import { inputClass } from '../../components/ui/classes';
import { CategoriesSection } from './CategoriesSection';
import { AccountSection } from './AccountSection';
import { BackupsSection } from './BackupsSection';
import { BirthdaysSection } from './BirthdaysSection';
import { DataSection } from './DataSection';
import { EmailSection } from './EmailSection';
import { SecuritySection } from './SecuritySection';
import { SessionSection } from './SessionSection';
import { HolidaysSection } from './HolidaysSection';
import { SettingsSection } from './SettingsSection';
import { VacationSection } from './VacationSection';

const LABELS: Record<Theme, string> = {
  system: 'System',
  light: 'Light',
  'light-contrast': 'Light (high contrast)',
  dim: 'Dim (greys and blues)',
  dark: 'Dark',
};
const POSITION_LABELS: Record<(typeof PILLS_POSITIONS)[number], string> = {
  top: 'Top',
  bottom: 'Bottom',
  left: 'Left (vertical)',
  right: 'Right (vertical)',
};
const PAST_STYLE_LABELS: Record<PastStyle, string> = {
  stripes: 'Diagonal stripes',
  crosshatch: 'Cross-hatch',
  line: 'Single diagonal line',
  cross: 'Cross (X)',
  fade: 'Fade the day',
};
const PAST_STRENGTH_LABELS: Record<PastStrength, string> = {
  light: 'Light',
  medium: 'Medium',
  strong: 'Strong',
};
const TODO_MARKER_LABELS: Record<TodoMarker, string> = {
  ring: 'Ring around the day number',
  bar: 'Coloured bar on the left',
  badge: 'Badge with the count',
  triangle: 'Corner triangle',
};
const MAX_EVENT_CHOICES = Array.from(
  { length: MAX_MAX_EVENTS - MIN_MAX_EVENTS + 1 },
  (_, i) => MIN_MAX_EVENTS + i,
);
const VERTICAL_SIZE_CHOICES = [10, 12, 14, 16, 18, 20, 24, 28, 32];
const SIZE_LABELS: Record<TextSize, string> = {
  small: 'Small',
  default: 'Default',
  large: 'Large',
  xlarge: 'Extra large',
};

export function SettingsPage() {
  const [theme, setTheme] = useTheme();
  const [textSize, setTextSize] = useTextSize();
  const [pillsPosition, setPillsPosition] = usePillsPosition();
  const [pillsWidth, setPillsWidth] = usePillsWidth();
  const [weekNumbers, setWeekNumbers] = useWeekNumbers();
  const [strikePast, setStrikePast] = useStrikePastSetting();
  const [pastStyle, setPastStyle] = usePastStyle();
  const [pastStrength, setPastStrength] = usePastStrength();
  const [pastStripe, setPastStripe] = usePastStripeColour();
  const [todoMarker, setTodoMarker] = useTodoMarker();
  const [todoColour, setTodoColour] = useTodoMarkerColour();
  const [showIcons, setShowIcons] = useShowCategoryIcons();
  const [iconsInCalendar, setIconsInCalendar] = useIconsInCalendar();
  const [iconsOnVertical, setIconsOnVertical] = useIconsOnVertical();
  const [maxEvents, setMaxEvents] = useMaxEvents();
  const [verticalSize, setVerticalSize] = useVerticalTextSize();
  // Links like /settings#vacation: scroll to the section once the page is there.
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView?.();
  }, [hash]);
  return (
    <section aria-labelledby="settings-heading" className="max-w-xl">
      <h1 id="settings-heading" className="text-lg font-semibold">
        Settings
      </h1>
      <div className="mt-4 space-y-4">
        <SettingsSection title="Appearance">
          <div>
            <label htmlFor="theme" className="block text-sm font-medium">
              Theme
            </label>
            <select
              id="theme"
              value={theme}
              onChange={(e) => setTheme(e.target.value as Theme)}
              className={`${inputClass} mt-2`}
            >
              {THEMES.map((t) => (
                <option key={t} value={t}>
                  {LABELS[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-4">
            <label htmlFor="text-size" className="block text-sm font-medium">
              Text size
            </label>
            <select
              id="text-size"
              value={textSize}
              onChange={(e) => setTextSize(e.target.value as TextSize)}
              className={`${inputClass} mt-2`}
            >
              {TEXT_SIZES.map((s) => (
                <option key={s} value={s}>
                  {SIZE_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-4">
            <label htmlFor="pills-position" className="block text-sm font-medium">
              Category pills
            </label>
            <select
              id="pills-position"
              value={pillsPosition}
              onChange={(e) => {
                if (isPillsPosition(e.target.value)) setPillsPosition(e.target.value);
              }}
              className={`${inputClass} mt-2`}
            >
              {PILLS_POSITIONS.map((position) => (
                <option key={position} value={position}>
                  {POSITION_LABELS[position]}
                </option>
              ))}
            </select>
            {pillsPosition === 'left' || pillsPosition === 'right' ? (
              <div className="mt-3 flex min-h-9 items-center gap-3 text-sm">
                <label htmlFor="pills-width" className="font-medium">
                  Column width
                </label>
                <input
                  id="pills-width"
                  type="range"
                  min={MIN_PILLS_WIDTH}
                  max={MAX_PILLS_WIDTH}
                  step={1}
                  value={pillsWidth}
                  onChange={(e) => setPillsWidth(Number(e.target.value))}
                  className="min-w-0 flex-1"
                />
                <output htmlFor="pills-width" className="w-12 tabular-nums text-text-muted">
                  {pillsWidth} rem
                </output>
              </div>
            ) : null}
            <p className="mt-1 text-xs text-text-muted">
              Where the category filter sits on the calendar, on this device. The phone layout
              always has it on top.
            </p>
          </div>
          <label className="mt-4 flex min-h-9 items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={weekNumbers}
              onChange={(e) => setWeekNumbers(e.target.checked)}
              className="size-4"
            />
            Show week numbers
          </label>
          <label className="mt-2 flex min-h-9 items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={strikePast}
              onChange={(e) => setStrikePast(e.target.checked)}
              className="size-4"
            />
            Strike through past days
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 pl-6 text-sm">
            <label htmlFor="past-style" className="flex items-center gap-2 font-medium">
              Past days style
              <select
                id="past-style"
                value={pastStyle}
                onChange={(e) => {
                  if (isPastStyle(e.target.value)) setPastStyle(e.target.value);
                }}
                className={`${inputClass} w-auto font-normal`}
              >
                {PAST_STYLES.map((style) => (
                  <option key={style} value={style}>
                    {PAST_STYLE_LABELS[style]}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="past-strength" className="flex items-center gap-2 font-medium">
              Strength
              <select
                id="past-strength"
                value={pastStrength}
                onChange={(e) => {
                  if (isPastStrength(e.target.value)) setPastStrength(e.target.value);
                }}
                className={`${inputClass} w-auto font-normal`}
              >
                {PAST_STRENGTHS.map((strength) => (
                  <option key={strength} value={strength}>
                    {PAST_STRENGTH_LABELS[strength]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="mt-2 flex min-h-9 items-center gap-2 pl-6 text-sm">
            <label htmlFor="past-stripe-colour" className="font-medium">
              Past days stripe colour
            </label>
            <input
              id="past-stripe-colour"
              type="color"
              value={pastStripe}
              onChange={(e) => setPastStripe(e.target.value)}
              className="h-8 w-12 cursor-pointer rounded border border-border bg-transparent p-0.5"
            />
            <button
              type="button"
              className="text-xs text-text-muted underline"
              onClick={() => setPastStripe(DEFAULT_PAST_STRIPE_COLOUR)}
            >
              Reset
            </button>
          </div>
          <p className="mt-1 pl-6 text-xs text-text-muted">
            Marks the days before today in the Months, Year and phone views. Fade does not use the
            colour. Saved to your account.
          </p>
          <div className="mt-4">
            <label htmlFor="todo-marker" className="block text-sm font-medium">
              To-do marker
            </label>
            <select
              id="todo-marker"
              value={todoMarker}
              onChange={(e) => {
                if (isTodoMarker(e.target.value)) setTodoMarker(e.target.value);
              }}
              className={`${inputClass} mt-2`}
            >
              {TODO_MARKERS.map((marker) => (
                <option key={marker} value={marker}>
                  {TODO_MARKER_LABELS[marker]}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-text-muted">
              How the Months and Year views mark days with open to-dos (due that day, or without a
              due date on today). Saved to your account.
            </p>
            <div className="mt-2 flex min-h-9 items-center gap-2 text-sm">
              <label htmlFor="todo-marker-colour" className="font-medium">
                Marker colour
              </label>
              <input
                id="todo-marker-colour"
                type="color"
                value={isHex(todoColour) ? todoColour : DEFAULT_TODO_MARKER_HEX}
                onChange={(e) => setTodoColour(e.target.value.toLowerCase())}
                className="h-8 w-12 cursor-pointer rounded border border-border bg-transparent p-0.5"
              />
              {isHex(todoColour) ? (
                <button
                  type="button"
                  className="text-xs text-text-muted underline"
                  onClick={() => setTodoColour(AUTO_TODO_MARKER_COLOUR)}
                >
                  Use the theme colour
                </button>
              ) : (
                <span className="text-xs text-text-muted">Theme colour (amber)</span>
              )}
            </div>
          </div>
          <label className="mt-2 flex min-h-9 items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={showIcons}
              onChange={(e) => setShowIcons(e.target.checked)}
              className="size-4"
            />
            Show category icons
          </label>
          <label className="flex min-h-9 items-center gap-2 pl-6 text-sm font-medium">
            <input
              type="checkbox"
              checked={iconsInCalendar}
              disabled={!showIcons}
              onChange={(e) => setIconsInCalendar(e.target.checked)}
              className="size-4"
            />
            Icons in the calendar and event lists
          </label>
          <label className="flex min-h-9 items-center gap-2 pl-12 text-sm font-medium">
            <input
              type="checkbox"
              checked={iconsOnVertical}
              disabled={!showIcons || !iconsInCalendar}
              onChange={(e) => setIconsOnVertical(e.target.checked)}
              className="size-4"
            />
            Icons on vertical event labels
          </label>
          <p className="pl-6 text-xs text-text-muted">
            Turn off “in the calendar” to keep the icons only in the category pills.
          </p>
          <div className="mt-4">
            <label htmlFor="max-events" className="block text-sm font-medium">
              Events shown per day
            </label>
            <select
              id="max-events"
              value={maxEvents}
              onChange={(e) => setMaxEvents(Number(e.target.value))}
              className={`${inputClass} mt-2`}
            >
              {MAX_EVENT_CHOICES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-text-muted">
              Desktop month grid; further events are counted as +N. Higher values make days taller.
            </p>
          </div>
          <div className="mt-4">
            <label htmlFor="vertical-size" className="block text-sm font-medium">
              Vertical event text size
            </label>
            <select
              id="vertical-size"
              value={verticalSize}
              onChange={(e) => setVerticalSize(Number(e.target.value))}
              className={`${inputClass} mt-2`}
            >
              {(VERTICAL_SIZE_CHOICES.includes(verticalSize)
                ? VERTICAL_SIZE_CHOICES
                : [...VERTICAL_SIZE_CHOICES, verticalSize].sort((a, b) => a - b)
              ).map((n) => (
                <option key={n} value={n}>
                  {n} px
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-text-muted">
              Shrinks automatically when the name does not fit the event's height
            </p>
          </div>
        </SettingsSection>
        <CategoriesSection />
        <VacationSection />
        <HolidaysSection />
        <BirthdaysSection />
        <AccountSection />
        <SecuritySection />
        <EmailSection />
        <DataSection />
        <BackupsSection />
        <SessionSection />
      </div>
    </section>
  );
}
