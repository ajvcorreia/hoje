import { createBooleanPreference } from './booleanPreference';

export const FIT_COLUMNS_KEY = 'hoje.fitColumns';

/** Widen each desktop month column so no event title is truncated (per device; off by default). */
const fitColumns = createBooleanPreference(FIT_COLUMNS_KEY, false);

export const readFitColumns = fitColumns.read;
export const storeFitColumns = fitColumns.store;
export const useFitColumns = fitColumns.use;
