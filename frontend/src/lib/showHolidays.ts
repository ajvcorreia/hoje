import { createBooleanPreference } from './booleanPreference';

export const SHOW_HOLIDAYS_KEY = 'hoje.showHolidays';

/** Draw holidays of enabled calendars in the calendar views (per device; on by default). */
const showHolidays = createBooleanPreference(SHOW_HOLIDAYS_KEY, true);

export const readShowHolidays = showHolidays.read;
export const storeShowHolidays = showHolidays.store;
export const useShowHolidays = showHolidays.use;
