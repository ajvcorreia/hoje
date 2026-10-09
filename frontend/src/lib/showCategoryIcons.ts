import { useMeSetting } from './meSetting';

/** Whether category glyphs are shown in the calendar, lists and filter pills (stored on the user). */
export function useShowCategoryIcons(): [boolean, (value: boolean) => void] {
  return useMeSetting('show_category_icons', true);
}
