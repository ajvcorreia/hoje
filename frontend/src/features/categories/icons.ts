import { useCallback } from 'react';
import { useShowCategoryIcons } from '../../lib/showCategoryIcons';
import { categoryMap, useCategories } from './api';

/** Glyphs offered when editing a category; any emoji pasted in the field works too. */
export const CATEGORY_ICONS = [
  '🏖️',
  '🎉',
  '❗',
  '📅',
  '👥',
  '✈️',
  '💰',
  '🏠',
  '🚗',
  '🎂',
  '🎓',
  '💼',
  '🏥',
  '🛒',
  '🍽️',
  '🎬',
  '🎵',
  '⚽',
  '📞',
  '✉️',
  '🔧',
  '🐾',
  '❤️',
  '⭐',
] as const;

/** Prefixes a title with the glyph, when there is one. */
export function withIcon(icon: string | null | undefined, title: string): string {
  return icon ? `${icon} ${title}` : title;
}

/**
 * Category id -> glyph to show, or undefined when the user switched icons off in Settings or the
 * category has none.
 */
export function useCategoryIcon(): (categoryId: string | undefined) => string | undefined {
  const { data: categories } = useCategories();
  const [enabled] = useShowCategoryIcons();
  const byId = categoryMap(categories);
  return useCallback(
    (categoryId) => (enabled && categoryId ? (byId.get(categoryId)?.icon ?? undefined) : undefined),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enabled, categories],
  );
}
