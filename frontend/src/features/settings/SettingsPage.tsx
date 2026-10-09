import { useEffect } from 'react';
import { useLocation } from 'react-router';
import { THEMES, type Theme } from '../../lib/theme';
import { TEXT_SIZES, type TextSize } from '../../lib/textSize';
import { useWeekNumbers } from '../../lib/weekNumbers';
import { useStrikePast } from '../../lib/strikePast';
import { DEFAULT_PAST_STRIPE_COLOUR, usePastStripeColour } from '../../lib/pastStripeColour';
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
  dark: 'Dark',
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
  const [weekNumbers, setWeekNumbers] = useWeekNumbers();
  const [strikePast, setStrikePast] = useStrikePast();
  const [pastStripe, setPastStripe] = usePastStripeColour();
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
