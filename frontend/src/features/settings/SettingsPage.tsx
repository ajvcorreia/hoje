import { THEMES, type Theme } from '../../lib/theme';
import { useTheme } from '../../app/useTheme';

const LABELS: Record<Theme, string> = { system: 'System', light: 'Light', dark: 'Dark' };

export function SettingsPage() {
  const [theme, setTheme] = useTheme();
  return (
    <section aria-labelledby="settings-heading">
      <h1 id="settings-heading" className="text-lg font-semibold">
        Settings
      </h1>
      <div className="mt-4 max-w-sm rounded-lg border border-border bg-surface p-4">
        <label htmlFor="theme" className="block text-sm font-medium">
          Theme
        </label>
        <select
          id="theme"
          value={theme}
          onChange={(e) => setTheme(e.target.value as Theme)}
          className="mt-2 min-h-11 w-full rounded-md border border-border bg-surface px-3 text-sm md:min-h-9"
        >
          {THEMES.map((t) => (
            <option key={t} value={t}>
              {LABELS[t]}
            </option>
          ))}
        </select>
      </div>
    </section>
  );
}
