import { useCallback, useState } from 'react';
import { applyTheme, readStoredTheme, storeTheme, type Theme } from '../lib/theme';

export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme);
  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    storeTheme(next);
    applyTheme(next);
  }, []);
  return [theme, setTheme];
}
