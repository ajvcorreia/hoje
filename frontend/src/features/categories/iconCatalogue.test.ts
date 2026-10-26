import { describe, expect, it } from 'vitest';
import { ICON_GROUPS, firstEmoji, searchIcons } from './iconCatalogue';

const all = ICON_GROUPS.flatMap((group) => group.icons.map(([icon]) => icon));
// The icons of the starter categories (backend/hoje/data/seed_categories.json) and birthdays.
const STARTER = ['🏖️', '🎉', '❗', '📅', '👥', '✈️', '💰', '🎂'];

describe('icon catalogue', () => {
  it('offers each glyph once, including every starter category icon', () => {
    expect(new Set(all).size).toBe(all.length);
    expect(all.length).toBeGreaterThanOrEqual(180);
    for (const icon of STARTER) expect(all).toContain(icon);
  });

  it('finds glyphs by every word typed, case-insensitively', () => {
    const icons = (query: string) => searchIcons(query).flatMap((g) => g.icons.map(([i]) => i));
    expect(icons('Birthday')).toEqual(['🎂']);
    expect(icons('red square')).toEqual(['🟥']);
    expect(searchIcons('zzz')).toEqual([]);
    expect(searchIcons('  ')).toHaveLength(ICON_GROUPS.length);
  });

  it('takes the first emoji of pasted text, flags and joined emoji whole', () => {
    expect(firstEmoji(' 🦄 ')).toBe('🦄');
    expect(firstEmoji('🇵🇹🇬🇧')).toBe('🇵🇹');
    expect(firstEmoji('👩‍💻 coding')).toBe('👩‍💻');
    expect(firstEmoji('1️⃣')).toBe('1️⃣');
    expect(firstEmoji('abc')).toBeNull();
    expect(firstEmoji('')).toBeNull();
  });
});
