import { describe, expect, it } from 'vitest';
import { todoAria, todoDays } from './todoDays';

const todo = (shown_on: string, due_date: string | null = null, done = false) => ({
  shown_on,
  due_date,
  done,
});

describe('todoDays', () => {
  it('counts undated to-dos on the day they are listed and dated ones on their due date', () => {
    const days = todoDays([
      todo('2026-06-15'),
      todo('2026-06-15'),
      todo('2026-06-15', '2026-06-20'),
      todo('2026-06-15', '2026-06-10'),
      todo('2026-06-15', '2026-06-20', true),
    ]);
    expect([...days]).toEqual([
      ['2026-06-15', 2],
      ['2026-06-20', 1],
      ['2026-06-10', 1],
    ]);
  });

  it('names the count for screen readers', () => {
    expect(todoAria(undefined)).toBe('');
    expect(todoAria(1)).toBe(', 1 to-do');
    expect(todoAria(3)).toBe(', 3 to-dos');
  });
});
