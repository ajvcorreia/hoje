import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  THEMES,
  THEME_STORAGE_KEY,
  applyTheme,
  isTheme,
  readStoredTheme,
  storeTheme,
} from './theme';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('theme persistence', () => {
  it('defaults to system', () => {
    expect(readStoredTheme()).toBe('system');
  });

  it('round-trips a stored theme', () => {
    storeTheme('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(readStoredTheme()).toBe('dark');
  });

  it('ignores invalid stored values', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'neon');
    expect(readStoredTheme()).toBe('system');
  });

  it('tolerates localStorage failures', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readStoredTheme()).toBe('system');
    expect(() => storeTheme('light')).not.toThrow();
  });

  it('lists the four themes including high-contrast light', () => {
    expect([...THEMES]).toEqual(['system', 'light', 'light-contrast', 'dark']);
    expect(isTheme('light-contrast')).toBe(true);
    expect(isTheme('contrast')).toBe(false);
  });

  it('round-trips the high-contrast theme', () => {
    storeTheme('light-contrast');
    expect(readStoredTheme()).toBe('light-contrast');
    applyTheme('light-contrast');
    expect(document.documentElement).toHaveAttribute('data-theme', 'light-contrast');
  });

  it('applies the theme to the html element', () => {
    applyTheme('dark');
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    applyTheme('system');
    expect(document.documentElement).toHaveAttribute('data-theme', 'system');
  });
});
