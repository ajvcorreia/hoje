import { createBooleanPreference } from './booleanPreference';

export const STRIKE_PAST_KEY = 'hoje.strikePast';

/**
 * This device's "Strike through past days" switch (off by default): used until the choice is saved
 * on the account, see `useStrikePastSetting` in pastDays.ts.
 */
const strikePast = createBooleanPreference(STRIKE_PAST_KEY, false);

export const readStrikePast = strikePast.read;
export const storeStrikePast = strikePast.store;
export const useStrikePast = strikePast.use;
