import { describe, expect, it } from 'vitest';
import { safeNext } from './safeNext';

describe('safeNext', () => {
  it('allows same-origin relative paths', () => {
    expect(safeNext('/settings')).toBe('/settings');
    expect(safeNext('/a?b=1#c')).toBe('/a?b=1#c');
  });

  it.each([
    '//evil.com',
    'https://evil.com',
    'javascript:alert(1)',
    '/\\evil.com',
    '',
    '/\n/evil.com',
  ])('rejects %j', (value) => {
    expect(safeNext(value)).toBe('/');
  });

  it('falls back for null and undefined', () => {
    expect(safeNext(null)).toBe('/');
    expect(safeNext(undefined, '/x')).toBe('/x');
  });
});
