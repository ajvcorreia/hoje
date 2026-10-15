import type { ImportResult } from './dataApi';

/** What an import would change. `eventsOnly` hides the rows a calendar file can never touch. */
export function ImportPreview({
  result,
  eventsOnly,
}: {
  result: ImportResult;
  eventsOnly?: boolean;
}) {
  const { categories, events, leave_policies: leave, holiday_calendars: calendars } = result;
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-text-muted">Categories</dt>
        <dd>
          {categories.create} new, {categories.reuse} matched to existing
        </dd>
        <dt className="text-text-muted">Events</dt>
        <dd>
          {events.create} to add, {events.skip_duplicate} already there (skipped)
        </dd>
        {eventsOnly ? null : (
          <>
            <dt className="text-text-muted">Leave allowances</dt>
            <dd>
              {leave.create} new, {leave.update} updated
            </dd>
            <dt className="text-text-muted">Holiday calendars</dt>
            <dd>{calendars.update} updated</dd>
            <dt className="text-text-muted">Time zone and weekend</dt>
            <dd>{result.settings.update ? 'will be updated' : 'unchanged'}</dd>
          </>
        )}
      </dl>
      {result.warnings.length > 0 ? (
        <ul aria-label="Warnings" className="list-disc space-y-1 pl-5 text-sm">
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
