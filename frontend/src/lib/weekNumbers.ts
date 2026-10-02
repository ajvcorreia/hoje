import { createBooleanPreference } from './booleanPreference';

export const WEEK_NUMBERS_KEY = 'hoje.weekNumbers';

/** Show the ISO week-number column (per device; on unless switched off). */
const weekNumbers = createBooleanPreference(WEEK_NUMBERS_KEY, true);

export const readWeekNumbers = weekNumbers.read;
export const storeWeekNumbers = weekNumbers.store;
export const useWeekNumbers = weekNumbers.use;
