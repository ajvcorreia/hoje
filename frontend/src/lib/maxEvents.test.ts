import { afterEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_MAX_EVENTS,
  MAX_EVENTS_KEY,
  clampMaxEvents,
  readMaxEvents,
  storeMaxEvents,
} from './maxEvents';

afterEach(() => window.localStorage.removeItem(MAX_EVENTS_KEY));

describe('max events per day', () => {
  it('defaults to two lanes', () => {
    expect(readMaxEvents()).toBe(DEFAULT_MAX_EVENTS);
    expect(DEFAULT_MAX_EVENTS).toBe(2);
  });

  it('stores and reads back a choice', () => {
    storeMaxEvents(5);
    expect(window.localStorage.getItem(MAX_EVENTS_KEY)).toBe('5');
    expect(readMaxEvents()).toBe(5);
  });

  it('clamps to 1-6 and ignores garbage', () => {
    expect(clampMaxEvents(0)).toBe(1);
    expect(clampMaxEvents(99)).toBe(6);
    expect(clampMaxEvents(3.4)).toBe(3);
    expect(clampMaxEvents('abc')).toBe(DEFAULT_MAX_EVENTS);
    window.localStorage.setItem(MAX_EVENTS_KEY, '40');
    expect(readMaxEvents()).toBe(6);
    window.localStorage.setItem(MAX_EVENTS_KEY, 'nope');
    expect(readMaxEvents()).toBe(DEFAULT_MAX_EVENTS);
  });
});
