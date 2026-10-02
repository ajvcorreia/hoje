import { THEMES, type Theme } from '../../lib/theme';
import { TEXT_SIZES, type TextSize } from '../../lib/textSize';
import { useWeekNumbers } from '../../lib/weekNumbers';
import { useTheme } from '../../app/useTheme';
import { useTextSize } from '../../app/useTextSize';
import { inputClass } from '../../components/ui/classes';
import { CategoriesSection } from './CategoriesSection';
import { AccountSection } from './AccountSection';
import { EmailSection } from './EmailSection';
import { SecuritySection } from './SecuritySection';
import { SessionSection } from './SessionSection';
import { SettingsSection } from './SettingsSection';

const LABELS: Record<Theme, string> = { system: 'System', light: 'Light', dark: 'Dark' };
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
        </SettingsSection>
        <CategoriesSection />
        <AccountSection />
        <SecuritySection />
        <EmailSection />
        <SessionSection />
      </div>
    </section>
  );
}
