import { useMeSetting } from './meSetting';

/** Whether category glyphs are shown in the calendar, lists and filter pills (stored on the user). */
export function useShowCategoryIcons(): [boolean, (value: boolean) => void] {
  return useMeSetting('show_category_icons', true);
}

/** Whether the glyphs are also drawn in the calendar and its lists (off: filter pills only). */
export function useIconsInCalendar(): [boolean, (value: boolean) => void] {
  return useMeSetting('icons_in_calendar', true);
}

/** Whether the glyphs are drawn on rotated (vertical) event labels. */
export function useIconsOnVertical(): [boolean, (value: boolean) => void] {
  return useMeSetting('icons_on_vertical', true);
}
