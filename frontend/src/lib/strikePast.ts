import { createBooleanPreference } from './booleanPreference';

export const STRIKE_PAST_KEY = 'hoje.strikePast';

/** Strike through every day before today in the month grid (per device; off by default). */
const strikePast = createBooleanPreference(STRIKE_PAST_KEY, false);

export const readStrikePast = strikePast.read;
export const storeStrikePast = strikePast.store;
export const useStrikePast = strikePast.use;
