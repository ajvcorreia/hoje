import { format } from 'date-fns';
import type { components } from '../../api/schema';
import { btnPrimary, linkClass } from '../../components/ui/classes';
import { describeError } from '../../lib/errors';
import { ApiError } from '../../api/client';
import { backupInProgress, useBackups, useRequestBackup } from './api';
import { RESTORE_GUIDE_URL, formatSize, formatWhen } from './backupFormat';
import { SettingsSection } from './SettingsSection';

type Run = components['schemas']['BackupRunOut'];

const STATUS_LABELS: Record<Run['status'], string> = {
  requested: 'Queued',
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
};

/** The Settings section for database backups. Renders nothing unless the user may see it. */
export function BackupsSection() {
  const backups = useBackups();
  const request = useRequestBackup();
  const status = backups.data;
  if (!status) return null; // loading, or 404 (not the owner), or unreachable

  const busy = backupInProgress(status) || request.isPending;
  const hour = String(status.schedule_hour).padStart(2, '0');

  return (
    <SettingsSection title="Backups" id="backups">
      {status.enabled ? (
        status.last_success ? (
          <p className={status.stale ? 'text-sm font-medium text-danger' : 'text-sm'}>
            Last backup: {formatWhen(status.last_success.finished_at)} ·{' '}
            {formatSize(status.last_success.size_bytes)}
            {status.stale ? ' (older than expected)' : ''}
          </p>
        ) : (
          <p className={status.stale ? 'text-sm font-medium text-danger' : 'text-sm'}>
            No backup yet
          </p>
        )
      ) : (
        <p className="text-sm">Backups are turned off on this server.</p>
      )}
      {status.stale ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          The last successful backup is more than 26 hours old. Check the worker log, or back up
          now.
        </p>
      ) : null}

      <p className="text-sm text-text-muted">
        {status.enabled
          ? `Every day at ${hour}:00 ${status.timezone}, keeping ${status.keep_days} days.`
          : 'Set HOJE_BACKUP_ENABLED=true on the server to turn them on.'}{' '}
        Stored on the server in {status.directory} (the worker&apos;s backup volume).
        {status.next_run_at ? ` Next backup: ${formatWhen(status.next_run_at)}.` : ''}
      </p>

      <div className="space-y-2">
        <button
          type="button"
          className={btnPrimary}
          disabled={busy || !status.enabled}
          onClick={() => request.mutate()}
        >
          Back up now
        </button>
        <div role="status" className="min-h-5 text-sm text-text-muted">
          {busy ? 'Backup in progress…' : null}
        </div>
        {request.isError ? (
          <p role="alert" className="text-sm text-danger">
            {request.error instanceof ApiError && request.error.status === 409
              ? (request.error.detail ?? 'A backup is already in progress.')
              : describeError(request.error)}
          </p>
        ) : null}
      </div>

      <RecentRuns runs={status.runs} />

      <p className="border-t border-border pt-4 text-sm text-text-muted">
        Restores are done from the server command line — see the{' '}
        <a className={linkClass} href={RESTORE_GUIDE_URL} target="_blank" rel="noreferrer noopener">
          restore guide
        </a>
        .
      </p>
    </SettingsSection>
  );
}

function RecentRuns({ runs }: { runs: Run[] }) {
  if (runs.length === 0) {
    return <p className="text-sm text-text-muted">No backup runs recorded yet.</p>;
  }
  return (
    <div className="space-y-2 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Recent backups</h3>
      <ul aria-label="Recent backups" className="divide-y divide-border text-sm">
        {runs.map((run) => (
          <li key={run.id} className="py-2">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <time dateTime={run.created_at} className="text-xs text-text-muted">
                {format(new Date(run.created_at), 'd MMM yyyy, HH:mm')}
              </time>
              <span className="text-xs text-text-muted">
                {run.trigger === 'manual' ? 'Manual' : 'Scheduled'}
              </span>
              <span
                className={
                  run.status === 'failed'
                    ? 'text-xs font-medium text-danger'
                    : 'text-xs font-medium'
                }
              >
                {STATUS_LABELS[run.status]}
              </span>
              {run.status === 'succeeded' && run.size_bytes != null ? (
                <span className="text-xs text-text-muted">{formatSize(run.size_bytes)}</span>
              ) : null}
            </div>
            {run.status === 'failed' && run.error ? (
              <div className="break-words text-xs text-danger">{run.error}</div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
