import { useCallback } from 'react';
import {
  useIconsInCalendar,
  useIconsOnVertical,
  useShowCategoryIcons,
} from '../../lib/showCategoryIcons';
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

/** Where a glyph is drawn: the filter pills, the calendar and its lists, or vertical labels. */
export type IconScope = 'pills' | 'calendar' | 'vertical';

/**
 * Category id -> glyph to show in `scope`, or undefined when the user switched icons off in
 * Settings (all of them, the calendar ones, or the vertical ones) or the category has none.
 */
export function useCategoryIcon(
  scope: IconScope,
): (categoryId: string | undefined) => string | undefined {
  const { data: categories } = useCategories();
  const [all] = useShowCategoryIcons();
  const [inCalendar] = useIconsInCalendar();
  const [onVertical] = useIconsOnVertical();
  const enabled =
    all && (scope === 'pills' || (inCalendar && (scope === 'calendar' || onVertical)));
  const byId = categoryMap(categories);
  return useCallback(
    (categoryId) => (enabled && categoryId ? (byId.get(categoryId)?.icon ?? undefined) : undefined),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enabled, categories],
  );
}
