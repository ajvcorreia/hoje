import { useMeSetting } from './meSetting';

/**
 * Draw each multi-day vertical event of the Months view as one box over its days, without the
 * gaps and day dividers between them (saved on the account; see calendar.css).
 */
export function useJoinVertical(): [boolean, (value: boolean) => void] {
  return useMeSetting('join_vertical_events', false);
}
