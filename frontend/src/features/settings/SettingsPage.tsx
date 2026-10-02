import { THEMES, type Theme } from '../../lib/theme';
import { useTheme } from '../../app/useTheme';
import { inputClass } from '../../components/ui/classes';
import { AccountSection } from './AccountSection';
import { EmailSection } from './EmailSection';
import { SecuritySection } from './SecuritySection';
import { SessionSection } from './SessionSection';
import { SettingsSection } from './SettingsSection';

const LABELS: Record<Theme, string> = { system: 'System', light: 'Light', dark: 'Dark' };

export function SettingsPage() {
  const [theme, setTheme] = useTheme();
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
        </SettingsSection>
        <AccountSection />
        <SecuritySection />
        <EmailSection />
        <SessionSection />
      </div>
    </section>
  );
}
