# Hoje export format (version 1)

`GET /api/v1/export` returns one JSON document (`Content-Disposition: attachment;
filename="hoje-export-YYYY-MM-DD.json"`, `Cache-Control: no-store`). `POST /api/v1/import` accepts
the same document. The format is stable: version 1 files stay importable, and new optional fields
may appear later (importers ignore fields they do not know).

## What is and is not in a file

Included: settings (time zone, weekend days), live categories, live events with their reminders,
yearly leave policies, and per holiday calendar its on/off state, colour and your changes to the
bundled holidays.

Never included: password hashes, two-factor secrets, recovery codes, sessions, throttle rows,
the email log, backup runs, user ids or any internal id. Birthdays synced from FelizAnniv and the
FelizAnniv connection (address, API key) are not exported either: they belong to FelizAnniv, and an
import never touches them (on a new server, connect FelizAnniv again in Settings). Categories are
tied to events by a file-local `key`, not by database id. Deleted (binned) events and categories
are not exported.

## Example

```json
{
  "format": "hoje-export",
  "version": 1,
  "exported_at": "2026-10-05T12:00:00Z",
  "app_version": "1.2.0",
  "settings": {
    "timezone": "Europe/Lisbon",
    "weekend_days": [6, 7],
    "max_events_per_day": 2,
    "vertical_text_size": 12,
    "daily_summary_enabled": false,
    "daily_summary_time": "07:00"
  },
  "categories": [
    {
      "key": "c1",
      "name": "Vacation",
      "colour": "teal",
      "icon": null,
      "sort_order": 0,
      "is_leave": true,
      "hidden": false
    }
  ],
  "events": [
    {
      "category": "c1",
      "title": "Summer break",
      "notes": null,
      "start_date": "2026-08-03",
      "end_date": "2026-08-14",
      "all_day": true,
      "start_time": null,
      "end_time": null,
      "timezone": "Europe/Lisbon",
      "repeat": "none",
      "repeat_until": null,
      "label_vertical": false,
      "day_order": 0,
      "reminders": [{ "offset_minutes": 1440 }]
    }
  ],
  "leave_policies": [{ "year": 2026, "allowance_days": 22.0, "carried_over_days": 3.0 }],
  "holiday_calendars": [
    {
      "code": "PT",
      "enabled": true,
      "colour": "green",
      "custom_holidays": [{ "date": "2026-06-01", "name": "Company day", "is_non_working": false }],
      "removed_bundled": [{ "date": "2026-04-25", "name": "Freedom Day" }],
      "edited_bundled": [{ "date": "2026-04-24", "name": "Freedom Day", "is_non_working": true }]
    }
  ]
}
```

## Fields

| Field | Notes |
|---|---|
| `format` | Must be `"hoje-export"`. |
| `version` | Must be `1`. |
| `exported_at`, `app_version` | Informational; ignored by the importer. |
| `settings.timezone` | IANA zone name. `settings.weekend_days`: unique ISO weekdays 1 (Mon) to 7 (Sun). `settings.max_events_per_day`: integer 1 to 6, optional (absent in older files). `settings.vertical_text_size`: integer 8 to 32 (px), optional (absent in older files). `settings.daily_summary_enabled`: boolean and `settings.daily_summary_time`: `"HH:MM"` (24 hour, in `settings.timezone`), both optional (absent in older files; an absent value keeps the current one). |
| `categories[].key` | 1 to 64 characters, unique in the file; referenced by `events[].category`. |
| `categories[]` | `name` 1 to 40 characters (unique, case-insensitive), `colour` one of the 20 palette keys (`slate red orange amber lime green teal cyan blue indigo violet pink rose fuchsia purple sky emerald yellow brown gray`), `icon` or `null`, `sort_order` >= 0, `is_leave`, `hidden`. |
| `events[]` | Same bounds as the API: `title` 1 to 200, `notes` <= 5000, dates between 1900-01-01 and 2200-12-31, `end_date` >= `start_date` and at most 366 days after it (defaults to `start_date`), `repeat` is `none`, `monthly` or `yearly`, `repeat_until` >= `start_date`, at most 5 distinct `reminders`. `day_order` is an integer 0 to 32767, optional (absent = 0): the user's own position of the event among those of a day (0 = never ordered; events sort by it first, then by the usual rules, so ordered events come after unordered ones). All-day events carry no times; timed events need `start_time` and `end_time` (without a UTC offset; on a single day `end_time` is after `start_time`). `timezone` is an IANA name (defaults to the importing user's, or to `settings.timezone` of the file). |
| `leave_policies[]` | `year` 2000 to 2100 (unique), `allowance_days` and `carried_over_days` between 0 and 366 with one decimal. |
| `holiday_calendars[]` | `code` (`PT`, `AE`; unknown codes are skipped with a warning), `enabled`, `colour`, and the deviations below. |

Global caps: at most 100 categories, 20 000 events, 200 leave policies, 10 holiday calendars and
2 000 each of custom, removed and edited holidays. The request body of the import is limited to
10 MB. Every event must reference a category `key` present in the file.

## Holiday deviations

Calendars start from the bundled data of the application (the same for everyone). The file stores
only what differs, so it stays small and keeps working when bundled data is refreshed:

* `custom_holidays`: holidays you added.
* `removed_bundled`: bundled holidays (date and name) that are no longer in your calendar. A bundled
  holiday you edited also appears here (as the original), together with an entry in
  `edited_bundled`.
* `edited_bundled`: bundled-source holidays that differ from the shipped ones (a new date, name or
  working-day flag), as they are now.

Applying a calendar means: delete the `removed_bundled` entries, then add the `edited_bundled` and
`custom_holidays` entries that are not already there.

## Import semantics

`POST /api/v1/import` with `{ "mode": "merge" | "replace", "dry_run": bool, "password"?: string,
"data": <document> }`. The whole document is validated first; one problem rejects everything with
a `422` whose `detail` names the item, for example `events[57].end_date: end_date must be on or
after start_date`. The write is one transaction. `dry_run: true` writes nothing and returns the
counts. Imports (dry runs included) are limited to 10 per hour per user.

**Merge** (default):

* Categories are matched to your live categories by name, case-insensitively. A match is reused
  unchanged (its colour is kept); other categories are appended after your own.
* An event is skipped when you already have a live event with the same category, title, start and
  end date, all-day flag, times and repeat. Everything else is added as a new event.
* Leave policies are set per year (the file wins). Time zone and weekend days are applied. Calendar
  `enabled` and `colour` are applied and the deviations are added as described above.

**Replace** needs `password` (not for a dry run):

* All your live events and categories are moved to the bin first (restorable for 30 days; restoring
  an event brings its category back if the name is free), then the file is imported as new. If the
  file has no categories a default one is created.
* Leave policies are replaced. Every holiday calendar is reset to the bundled data, then the file's
  `enabled`, `colour` and deviations are applied (calendars not in the file end up disabled).

A successful import publishes one realtime change (`entity: "data"`), which makes open browsers
refresh everything.

## Limits worth knowing

A file with many events that all carry long notes can exceed the 10 MB import limit; split it or
shorten the notes.
