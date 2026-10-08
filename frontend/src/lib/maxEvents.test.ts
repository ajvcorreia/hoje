import { describe, expect, it } from 'vitest';
import { DEFAULT_MAX_EVENTS, clampMaxEvents } from './maxEvents';

describe('max events per day', () => {
  it('defaults to two lanes', () => {
    expect(DEFAULT_MAX_EVENTS).toBe(2);
  });

  it('clamps to 1-6 and ignores garbage', () => {
    expect(clampMaxEvents(0)).toBe(1);
    expect(clampMaxEvents(99)).toBe(6);
    expect(clampMaxEvents(3.4)).toBe(3);
    expect(clampMaxEvents('abc')).toBe(DEFAULT_MAX_EVENTS);
    expect(clampMaxEvents(undefined)).toBe(DEFAULT_MAX_EVENTS);
  });
});
