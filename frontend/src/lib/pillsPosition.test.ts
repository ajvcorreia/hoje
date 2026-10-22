import { afterEach, describe, expect, it } from 'vitest';
import {
  PILLS_POSITION_KEY,
  isPillsPosition,
  readPillsPosition,
  storePillsPosition,
} from './pillsPosition';

describe('pills position', () => {
  afterEach(() => window.localStorage.clear());

  it('is top until chosen, and ignores anything it does not know', () => {
    expect(readPillsPosition()).toBe('top');
    window.localStorage.setItem(PILLS_POSITION_KEY, 'diagonal');
    expect(readPillsPosition()).toBe('top');
    expect(isPillsPosition('left')).toBe(true);
    expect(isPillsPosition('middle')).toBe(false);
  });

  it('remembers the choice', () => {
    storePillsPosition('right');
    expect(readPillsPosition()).toBe('right');
    expect(window.localStorage.getItem(PILLS_POSITION_KEY)).toBe('right');
  });
});
