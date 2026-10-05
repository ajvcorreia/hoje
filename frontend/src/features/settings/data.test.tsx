import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, problem, renderApp, type RecordedCall } from '../../test/utils';
import { keysForChange } from '../realtime/realtimeKeys';

const base = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/me': ME,
  'GET /api/v1/settings/email': { configured: true, from_address: 'hoje@example.com' },
  'GET /api/v1/settings/email/log': [],
};

const PREVIEW = {
  mode: 'merge',
  dry_run: true,
  categories: { create: 1, reuse: 2 },
  events: { create: 3, skip_duplicate: 4 },
  leave_policies: { create: 1, update: 1 },
  holiday_calendars: { update: 2 },
  settings: { update: true },
  warnings: ["Category 'Work' already exists and is kept as it is (leave category: no)."],
};

const DOCUMENT = { format: 'hoje-export', version: 1, categories: [], events: [] };

function jsonFile(content: unknown = DOCUMENT, name = 'hoje.json') {
  return new File([JSON.stringify(content)], name, { type: 'application/json' });
}

async function chooseFile(file: File) {
  const input = await screen.findByLabelText('Export file to import');
  await userEvent.upload(input, file);
}

/** Replies to dry runs with PREVIEW (mode echoed) and to real runs with `final`. */
function importReply(final: Record<string, unknown> | Response) {
  return (call: RecordedCall) => {
    const body = call.body as { mode: string; dry_run: boolean };
    if (body.dry_run) return { ...PREVIEW, mode: body.mode };
    return final;
  };
}

const downloads: string[] = [];

beforeEach(() => {
  downloads.length = 0;
  URL.createObjectURL = vi.fn(() => 'blob:hoje-test');
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    downloads.push(this.download);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('export', () => {
  it('downloads the file under the name the server suggests and frees the object URL', async () => {
    mockApi({
      ...base,
      'GET /api/v1/export': () =>
        new Response(JSON.stringify(DOCUMENT), {
          headers: {
            'content-type': 'application/json',
            'content-disposition': 'attachment; filename="hoje-export-2026-10-05.json"',
          },
        }),
    });
    renderApp('/settings');
    expect(await screen.findByText(/never included/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Export my data' }));
    await waitFor(() => expect(downloads).toEqual(['hoje-export-2026-10-05.json']));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:hoje-test');
    expect(await screen.findByText('Downloaded hoje-export-2026-10-05.json')).toBeInTheDocument();
  });

  it('shows an alert when the export fails', async () => {
    mockApi({ ...base, 'GET /api/v1/export': problem(429, 'slow down', { 'retry-after': '120' }) });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: 'Export my data' }));
    expect(await screen.findByText(/Too many attempts/)).toBeInTheDocument();
    expect(downloads).toEqual([]);
  });
});

describe('import', () => {
  it('rejects a file over 10 MB without calling the server', async () => {
    const api = mockApi({ ...base });
    renderApp('/settings');
    const big = jsonFile();
    Object.defineProperty(big, 'size', { value: 12_500_000 });
    await chooseFile(big);
    expect(
      await screen.findByText(/12\.5 MB\. Files over 10 MB cannot be imported/),
    ).toHaveAttribute('role', 'alert');
    expect(api.callsTo('POST', '/api/v1/import')).toHaveLength(0);
  });

  it('explains a file that is not JSON', async () => {
    const api = mockApi({ ...base });
    renderApp('/settings');
    await chooseFile(new File(['{ nope'], 'broken.json', { type: 'application/json' }));
    expect(await screen.findByText(/not valid JSON/)).toBeInTheDocument();
    expect(api.callsTo('POST', '/api/v1/import')).toHaveLength(0);
  });

  it('runs a dry run automatically and previews the counts and warnings', async () => {
    const api = mockApi({ ...base, 'POST /api/v1/import': importReply(PREVIEW) });
    renderApp('/settings');
    await chooseFile(jsonFile());
    const heading = await screen.findByRole('heading', {
      name: 'What importing hoje.json would do',
    });
    await waitFor(() => expect(heading).toHaveFocus());
    const card = heading.closest('section')!;
    expect(within(card).getByText('1 new, 2 matched to existing')).toBeInTheDocument();
    expect(within(card).getByText('3 to add, 4 already there (skipped)')).toBeInTheDocument();
    expect(within(card).getByText('1 new, 1 updated')).toBeInTheDocument();
    expect(within(card).getByText('2 updated')).toBeInTheDocument();
    expect(within(card).getByText('will be updated')).toBeInTheDocument();
    expect(within(card).getByText(/Category 'Work' already exists/)).toBeInTheDocument();
    expect(within(card).getByRole('radio', { name: /^Merge/ })).toBeChecked();

    const calls = api.callsTo('POST', '/api/v1/import');
    expect(calls).toHaveLength(1);
    expect(calls[0]?.body).toEqual({ mode: 'merge', dry_run: true, data: DOCUMENT });
  });

  it('imports in merge mode and reports the result', async () => {
    const final = { ...PREVIEW, dry_run: false, warnings: [] };
    const api = mockApi({ ...base, 'POST /api/v1/import': importReply(final) });
    renderApp('/settings');
    await chooseFile(jsonFile());
    await userEvent.click(await screen.findByRole('button', { name: 'Import' }));
    expect(
      await screen.findByText(
        'Import finished: 3 events and 1 category added, 4 duplicates skipped.',
      ),
    ).toBeInTheDocument();
    const calls = api.callsTo('POST', '/api/v1/import');
    expect(calls).toHaveLength(2);
    expect(calls[1]?.body).toEqual({ mode: 'merge', dry_run: false, data: DOCUMENT });
    expect(screen.queryByRole('radio', { name: /^Merge/ })).not.toBeInTheDocument();
  });

  it('needs the password to replace, and warns about the bin', async () => {
    const final = { ...PREVIEW, mode: 'replace', dry_run: false, warnings: [] };
    const api = mockApi({ ...base, 'POST /api/v1/import': importReply(final) });
    renderApp('/settings');
    await chooseFile(jsonFile());
    await userEvent.click(await screen.findByRole('radio', { name: /^Replace/ }));
    expect(
      await screen.findByText('Your current events and categories will be moved to the bin first.'),
    ).toBeInTheDocument();
    const importButton = screen.getByRole('button', { name: 'Import' });
    expect(importButton).toBeDisabled();
    // The preview for replace was requested (a second dry run), without any password.
    await waitFor(() => expect(api.callsTo('POST', '/api/v1/import')).toHaveLength(2));
    expect(api.callsTo('POST', '/api/v1/import')[1]?.body).toEqual({
      mode: 'replace',
      dry_run: true,
      data: DOCUMENT,
    });

    await userEvent.type(screen.getByLabelText('Your password'), 'hunter2 hunter2');
    expect(importButton).toBeEnabled();
    await userEvent.click(importButton);
    expect(await screen.findByText(/^Import finished/)).toBeInTheDocument();
    expect(api.callsTo('POST', '/api/v1/import')[2]?.body).toEqual({
      mode: 'replace',
      dry_run: false,
      data: DOCUMENT,
      password: 'hunter2 hunter2',
    });
  });

  it('says so when the password is wrong', async () => {
    mockApi({
      ...base,
      'POST /api/v1/import': importReply(problem(400, 'Incorrect password or code')),
    });
    renderApp('/settings');
    await chooseFile(jsonFile());
    await userEvent.click(await screen.findByRole('radio', { name: /^Replace/ }));
    await userEvent.type(await screen.findByLabelText('Your password'), 'nope');
    await userEvent.click(screen.getByRole('button', { name: 'Import' }));
    const alert = await screen.findByText('Incorrect password.');
    expect(alert).toHaveAttribute('role', 'alert');
  });

  it("shows the server's path-specific message on a 422", async () => {
    const message = 'events[57].end_date: end_date must be on or after start_date';
    const api = mockApi({ ...base, 'POST /api/v1/import': problem(422, message) });
    renderApp('/settings');
    await chooseFile(jsonFile());
    const alert = await screen.findByText(message);
    expect(alert).toHaveAttribute('role', 'alert');
    expect(screen.queryByRole('button', { name: 'Import' })).not.toBeInTheDocument();
    expect(api.callsTo('POST', '/api/v1/import')).toHaveLength(1);
  });
});

describe('realtime', () => {
  it('invalidates every query when the data entity changes', () => {
    const keys = keysForChange({
      entity: 'data',
      op: 'update',
      id: 'x',
      version: 0,
      client_id: null,
    });
    expect(keys).toEqual([[]]);
  });
});
