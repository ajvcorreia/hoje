import { createBooleanPreference } from './booleanPreference';

export const SHOW_BIRTHDAYS_KEY = 'hoje.showBirthdays';

/** Draw synced FelizAnniv birthdays in the calendar views (per device, like holidays; on by default). */
const showBirthdays = createBooleanPreference(SHOW_BIRTHDAYS_KEY, true);

export const readShowBirthdays = showBirthdays.read;
export const storeShowBirthdays = showBirthdays.store;
export const useShowBirthdays = showBirthdays.use;
