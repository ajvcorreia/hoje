import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { format } from 'date-fns';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ME, authState, mockApi, problem, renderApp } from '../../test/utils';
import { keysForChange } from '../realtime/realtimeKeys';
import { formatSize } from './backupFormat';

const base = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/me': ME,
  'GET /api/v1/settings/email': { configured: true, from_address: 'hoje@example.com' },
  'GET /api/v1/settings/email/log': [],
};

function iso(offsetMs = 0) {
  return new Date(Date.now() + offsetMs).toISOString();
}

function run(overrides: Record<string, unknown> = {}) {
  return {
    id: crypto.randomUUID(),
    trigger: 'schedule',
    status: 'succeeded',
    created_at: iso(-60_000),
    started_at: iso(-60_000),
    finished_at: iso(-50_000),
    file_name: 'hoje-20261005-020000.dump',
    size_bytes: 1_258_291,
    error: null,
    ...overrides,
  };
}

function status(overrides: Record<string, unknown> = {}) {
  const finished = iso(-10_000);
  return {
    enabled: true,
    directory: '/backups',
    schedule_hour: 2,
    keep_days: 14,
    timezone: 'Asia/Dubai',
    next_run_at: iso(3_600_000),
    last_success: { finished_at: finished, file_name: 'hoje-x.dump', size_bytes: 1_258_291 },
    stale: false,
    runs: [run({ finished_at: finished })],
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('backups settings', () => {
  it('is hidden when the server answers 404 (not the owner)', async () => {
    const api = mockApi({ ...base, 'GET /api/v1/backups': problem(404, 'Not found') });
    renderApp('/settings');
    await screen.findByRole('heading', { name: 'Email' });
    await waitFor(() => expect(api.callsTo('GET', '/api/v1/backups')).toHaveLength(1));
    expect(screen.queryByRole('heading', { name: 'Backups' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Back up now' })).not.toBeInTheDocument();
  });

  it('shows the last backup, the schedule, where it is stored and the restore guide', async () => {
    // Pin the clock mid-day: the fixture finished a few seconds "ago", which must not cross a
    // minute boundary (or midnight) between building it and asserting on it.
    vi.useFakeTimers({ toFake: ['Date'], now: new Date(2026, 9, 5, 12, 0, 30) });
    const fixture = status();
    mockApi({ ...base, 'GET /api/v1/backups': fixture });
    renderApp('/settings');
    const section = (await screen.findByRole('heading', { name: 'Backups' })).closest('section')!;
    const finishedAt = format(new Date(fixture.last_success.finished_at), 'HH:mm');
    expect(
      within(section).getByText(`Last backup: today ${finishedAt} · 1.2 MB`),
    ).toBeInTheDocument();
    expect(
      within(section).getByText(/Every day at 02:00 Asia\/Dubai, keeping 14 days\./),
    ).toBeInTheDocument();
    expect(within(section).getByText(/Stored on the server in \/backups/)).toBeInTheDocument();
    expect(within(section).queryByRole('alert')).not.toBeInTheDocument();
    expect(
      within(section).getByText(/Restores are done from the server command line/),
    ).toBeVisible();
    expect(within(section).getByRole('link', { name: 'restore guide' })).toHaveAttribute(
      'href',
      'https://github.com/ajvcorreia/hoje/blob/main/deploy/backup/restore.md',
    );
    expect(within(section).getByRole('button', { name: 'Back up now' })).toBeEnabled();
    const list = within(section).getByRole('list', { name: 'Recent backups' });
    expect(within(list).getByText('Scheduled')).toBeInTheDocument();
    expect(within(list).getByText('Succeeded')).toBeInTheDocument();
  });

  it('says there is no backup yet and warns when the data is stale', async () => {
    mockApi({
      ...base,
      'GET /api/v1/backups': status({ last_success: null, stale: true, runs: [] }),
    });
    renderApp('/settings');
    const section = (await screen.findByRole('heading', { name: 'Backups' })).closest('section')!;
    expect(within(section).getByText('No backup yet')).toBeInTheDocument();
    expect(within(section).getByRole('alert')).toHaveTextContent(/more than 26 hours/);
    expect(within(section).getByText('No backup runs recorded yet.')).toBeInTheDocument();
  });

  it('warns about an old backup but keeps showing it', async () => {
    mockApi({ ...base, 'GET /api/v1/backups': status({ stale: true }) });
    renderApp('/settings');
    const section = (await screen.findByRole('heading', { name: 'Backups' })).closest('section')!;
    expect(
      within(section).getByText(/Last backup: today .* \(older than expected\)/),
    ).toBeVisible();
    expect(within(section).getByRole('alert')).toBeInTheDocument();
  });

  it('requests a backup, disables the button while it runs and shows the result', async () => {
    let runs = [run({ trigger: 'schedule' })];
    const api = mockApi({
      ...base,
      'GET /api/v1/backups': () => status({ runs }),
      'POST /api/v1/backups': () => {
        const queued = run({
          trigger: 'manual',
          status: 'requested',
          finished_at: null,
          file_name: null,
          size_bytes: null,
        });
        runs = [queued, ...runs];
        return new Response(JSON.stringify(queued), {
          status: 202,
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    const { queryClient } = renderApp('/settings');
    const button = await screen.findByRole('button', { name: 'Back up now' });
    await userEvent.click(button);
    await waitFor(() => expect(api.callsTo('POST', '/api/v1/backups')).toHaveLength(1));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Back up now' })).toBeDisabled());
    expect(await screen.findByText('Backup in progress…')).toBeInTheDocument();
    expect(screen.getByText('Queued')).toBeInTheDocument();
    expect(screen.getByText('Manual')).toBeInTheDocument();

    // The worker finishes; a realtime `backup_run` change invalidates ['backups'].
    expect(
      keysForChange({ entity: 'backup_run', op: 'update', id: 'x', version: 0, client_id: null }),
    ).toEqual([['backups']]);
    runs = runs.map((r, i) =>
      i === 0 ? { ...r, status: 'succeeded', finished_at: iso(), size_bytes: 2048 } : r,
    );
    await queryClient.invalidateQueries({ queryKey: ['backups'] });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Back up now' })).toBeEnabled());
    expect(screen.getAllByText('Succeeded')).toHaveLength(2);
    expect(screen.queryByText('Backup in progress…')).not.toBeInTheDocument();
  });

  it('shows the error of a failed run', async () => {
    mockApi({
      ...base,
      'GET /api/v1/backups': status({
        runs: [
          run({
            status: 'failed',
            trigger: 'manual',
            error: 'pg_dump failed: connection refused',
            file_name: null,
            size_bytes: null,
          }),
        ],
      }),
    });
    renderApp('/settings');
    const list = await screen.findByRole('list', { name: 'Recent backups' });
    expect(within(list).getByText('Failed')).toBeInTheDocument();
    expect(within(list).getByText('pg_dump failed: connection refused')).toBeInTheDocument();
  });

  it('shows a conflict from the server and keeps the button usable', async () => {
    mockApi({
      ...base,
      'GET /api/v1/backups': status(),
      'POST /api/v1/backups': problem(409, 'A backup is already queued or running'),
    });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: 'Back up now' }));
    expect(await screen.findByText('A backup is already queued or running')).toBeInTheDocument();
  });

  it('disables "Back up now" when backups are turned off on the server', async () => {
    mockApi({
      ...base,
      'GET /api/v1/backups': status({ enabled: false, next_run_at: null, stale: false }),
    });
    renderApp('/settings');
    expect(await screen.findByText('Backups are turned off on this server.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back up now' })).toBeDisabled();
  });
});

describe('formatSize', () => {
  it('uses binary units', () => {
    expect(formatSize(512)).toBe('512 B');
    expect(formatSize(1536)).toBe('1.5 KB');
    expect(formatSize(1_258_291)).toBe('1.2 MB');
    expect(formatSize(52_428_800)).toBe('50 MB');
  });
});
