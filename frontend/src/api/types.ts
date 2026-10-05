import type { components } from './schema';

type Schemas = components['schemas'];

export type AuthState = Schemas['AuthState'];
export type Me = Schemas['Me'];
export type Category = Schemas['Category'];
export type CategoryCreate = Schemas['CategoryCreate'];
export type CategoryUpdate = Schemas['CategoryUpdate'];
export type Event = Schemas['Event'];
export type EventCreate = Schemas['EventCreate'];
export type EventUpdate = Schemas['EventUpdate'];
export type EventWithImpact = Schemas['EventWithImpact'];
export type EventConflict = Schemas['EventConflict'];
export type Occurrence = Schemas['Occurrence'];
export type OccurrenceList = Schemas['OccurrenceList'];
export type SearchResult = Schemas['SearchResult'];
export type LeaveImpact = Schemas['LeaveImpact'];
export type LeaveBalance = Schemas['LeaveBalance'];
export type LeavePolicy = Schemas['LeavePolicy'];
export type Holiday = Schemas['Holiday'];
export type HolidayCalendar = Schemas['HolidayCalendar'];
export type Problem = Schemas['Problem'];
export type BirthdayOccurrence = Schemas['BirthdayOccurrence'];
export type FelizAnnivStatus = Schemas['FelizAnnivStatus'];
