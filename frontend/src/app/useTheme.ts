import { useEffect, useRef, useState } from 'react';
import { useMeSetting } from '../lib/meSetting';
import { applyTheme, isTheme, readStoredTheme, storeTheme, type Theme } from '../lib/theme';
import { useAuthState } from './useAuthState';

/**
 * The colour theme, stored on the account so it follows the user to every device. The device
 * also keeps a copy in localStorage, which main.tsx applies before the first paint (and which
 * is all there is while signed out).
 */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const [account, setAccount] = useMeSetting('theme', null);
  const [local, setLocal] = useState<Theme>(readStoredTheme);
  const theme = isTheme(account) ? account : local;
  const setTheme = (next: Theme) => {
    setLocal(next);
    storeTheme(next);
    applyTheme(next);
    setAccount(next);
  };
  return [theme, setTheme];
}

/**
 * Keeps this device on the account's theme: applies it when the user loads or it changes on
 * another device. An account without a theme yet takes this device's choice, once, so a theme
 * picked before themes followed the user is not lost.
 */
export function useThemeSync(): void {
  const { data } = useAuthState();
  const signedIn = Boolean(data?.user);
  const account = data?.user?.theme;
  const [, setAccount] = useMeSetting('theme', null);
  const save = useRef(setAccount);
  const offered = useRef(false);
  useEffect(() => {
    save.current = setAccount;
  });

  useEffect(() => {
    if (!signedIn) return;
    if (isTheme(account)) {
      if (account !== readStoredTheme()) storeTheme(account);
      applyTheme(account);
      return;
    }
    if (offered.current) return;
    offered.current = true;
    const local = readStoredTheme();
    if (local !== 'system') save.current(local);
  }, [signedIn, account]);
}
