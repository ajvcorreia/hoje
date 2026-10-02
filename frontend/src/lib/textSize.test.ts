import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  TEXT_SIZE_STORAGE_KEY,
  applyTextSize,
  readStoredTextSize,
  storeTextSize,
} from './textSize';

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('text size persistence', () => {
  it('defaults to default', () => {
    expect(readStoredTextSize()).toBe('default');
  });

  it('round-trips a stored size and ignores invalid values', () => {
    storeTextSize('large');
    expect(window.localStorage.getItem(TEXT_SIZE_STORAGE_KEY)).toBe('large');
    expect(readStoredTextSize()).toBe('large');
    window.localStorage.setItem(TEXT_SIZE_STORAGE_KEY, 'huge');
    expect(readStoredTextSize()).toBe('default');
  });

  it('tolerates localStorage failures', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readStoredTextSize()).toBe('default');
    expect(() => storeTextSize('xlarge')).not.toThrow();
  });

  it('applies the size to the html element', () => {
    applyTextSize('xlarge');
    expect(document.documentElement).toHaveAttribute('data-text-size', 'xlarge');
  });
});
