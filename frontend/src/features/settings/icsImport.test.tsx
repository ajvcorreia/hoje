import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ME, authState, mockApi, problem, renderApp, type RecordedCall } from '../../test/utils';

const base = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/me': ME,
  'GET /api/v1/settings/email': { configured: true, from_address: 'hoje@example.com' },
  'GET /api/v1/settings/email/log': [],
};

const PREVIEW = {
  mode: 'merge',
  dry_run: true,
  categories: { create: 1, reuse: 0 },
  events: { create: 12, skip_duplicate: 3 },
  leave_policies: { create: 0, update: 0 },
  holiday_calendars: { update: 0 },
  settings: { update: false },
  warnings: ['2 cancelled events left out.'],
};

const ICS = 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n';

function icsFile(content = ICS, name = 'work.ics') {
  return new File([content], name, { type: 'text/calendar' });
}

async function chooseFile(file: File) {
  const input = await screen.findByLabelText('Calendar file to import');
  await userEvent.upload(input, file);
}

/** Dry runs get PREVIEW; real runs get `final`. */
function reply(final: Record<string, unknown> | Response) {
  return (call: RecordedCall) => {
    const body = call.body as { dry_run: boolean };
    return body.dry_run ? PREVIEW : final;
  };
}

describe('calendar file import', () => {
  it('rejects text that is not an iCalendar file without calling the server', async () => {
    const api = mockApi({ ...base });
    renderApp('/settings');
    await chooseFile(icsFile('hello', 'notes.ics'));
    expect(await screen.findByText('This is not an iCalendar (.ics) file.')).toHaveAttribute(
      'role',
      'alert',
    );
    expect(api.callsTo('POST', '/api/v1/import/ics')).toHaveLength(0);
  });

  it('rejects a file over 8 MB without calling the server', async () => {
    const api = mockApi({ ...base });
    renderApp('/settings');
    const big = icsFile();
    Object.defineProperty(big, 'size', { value: 9_100_000 });
    await chooseFile(big);
    expect(
      await screen.findByText(/9\.1 MB\. Calendar files over 8 MB cannot be imported/),
    ).toHaveAttribute('role', 'alert');
    expect(api.callsTo('POST', '/api/v1/import/ics')).toHaveLength(0);
  });

  it('previews the events with a dry run in the default category', async () => {
    const api = mockApi({ ...base, 'POST /api/v1/import/ics': reply(PREVIEW) });
    renderApp('/settings');
    await chooseFile(icsFile());
    const heading = await screen.findByRole('heading', {
      name: 'What importing work.ics would do',
    });
    await waitFor(() => expect(heading).toHaveFocus());
    const card = heading.closest('section')!;
    expect(within(card).getByText('1 new, 0 matched to existing')).toBeInTheDocument();
    expect(within(card).getByText('12 to add, 3 already there (skipped)')).toBeInTheDocument();
    expect(within(card).getByText('2 cancelled events left out.')).toBeInTheDocument();
    expect(within(card).queryByText('Leave allowances')).not.toBeInTheDocument();
    expect(within(card).getByLabelText('Add the events to this category')).toHaveValue('Imported');

    const calls = api.callsTo('POST', '/api/v1/import/ics');
    expect(calls).toHaveLength(1);
    expect(calls[0]?.body).toEqual({ ics: ICS, category: 'Imported', dry_run: true });
  });

  it('checks again when the category changes and imports into that category', async () => {
    const final = { ...PREVIEW, dry_run: false, warnings: [] };
    const api = mockApi({ ...base, 'POST /api/v1/import/ics': reply(final) });
    renderApp('/settings');
    await chooseFile(icsFile());
    const field = await screen.findByLabelText('Add the events to this category');
    await screen.findByText('12 to add, 3 already there (skipped)');

    await userEvent.clear(field);
    await userEvent.type(field, 'Work');
    await waitFor(() =>
      expect(api.callsTo('POST', '/api/v1/import/ics').map((c) => c.body)).toContainEqual({
        ics: ICS,
        category: 'Work',
        dry_run: true,
      }),
    );
    const importButton = screen.getByRole('button', { name: 'Import' });
    await waitFor(() => expect(importButton).toBeEnabled());
    await userEvent.click(importButton);

    expect(
      await screen.findByText(
        'Import finished: 12 events and 1 category added, 3 duplicates skipped.',
      ),
    ).toBeInTheDocument();
    const real = api
      .callsTo('POST', '/api/v1/import/ics')
      .filter((c) => !(c.body as { dry_run: boolean }).dry_run);
    expect(real).toHaveLength(1);
    expect(real[0]?.body).toEqual({ ics: ICS, category: 'Work', dry_run: false });
    expect(screen.queryByRole('heading', { name: /What importing/ })).not.toBeInTheDocument();
  });

  it('will not import with a blank category', async () => {
    mockApi({ ...base, 'POST /api/v1/import/ics': reply(PREVIEW) });
    renderApp('/settings');
    await chooseFile(icsFile());
    const field = await screen.findByLabelText('Add the events to this category');
    await screen.findByText('12 to add, 3 already there (skipped)');
    await userEvent.clear(field);
    expect(await screen.findByText('Enter 1 to 40 characters.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
  });

  it('shows the server message when the file cannot be read', async () => {
    mockApi({
      ...base,
      'POST /api/v1/import/ics': problem(422, 'This does not look like an iCalendar (.ics) file.'),
    });
    renderApp('/settings');
    await chooseFile(icsFile('BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n'));
    expect(
      await screen.findByText(/does not look like an iCalendar \(\.ics\) file/),
    ).toBeInTheDocument();
  });

  it('cancel discards the file', async () => {
    mockApi({ ...base, 'POST /api/v1/import/ics': reply(PREVIEW) });
    renderApp('/settings');
    await chooseFile(icsFile());
    await screen.findByText('12 to add, 3 already there (skipped)');
    const heading = screen.getByRole('heading', { name: 'What importing work.ics would do' });
    const card = heading.closest('section')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('heading', { name: /What importing/ })).not.toBeInTheDocument();
  });
});
