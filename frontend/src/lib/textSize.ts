export const TEXT_SIZES = ['small', 'default', 'large', 'xlarge'] as const;
export type TextSize = (typeof TEXT_SIZES)[number];

export const TEXT_SIZE_STORAGE_KEY = 'hoje.textSize';

export function isTextSize(value: unknown): value is TextSize {
  return typeof value === 'string' && (TEXT_SIZES as readonly string[]).includes(value);
}

export function readStoredTextSize(): TextSize {
  try {
    const value = window.localStorage.getItem(TEXT_SIZE_STORAGE_KEY);
    return isTextSize(value) ? value : 'default';
  } catch {
    return 'default';
  }
}

export function storeTextSize(size: TextSize): void {
  try {
    window.localStorage.setItem(TEXT_SIZE_STORAGE_KEY, size);
  } catch {
    // Storage may be unavailable; the size still applies for this session.
  }
}

/** Sets `data-text-size` on <html>; static CSS maps it to the root font-size. */
export function applyTextSize(size: TextSize): void {
  document.documentElement.setAttribute('data-text-size', size);
}
