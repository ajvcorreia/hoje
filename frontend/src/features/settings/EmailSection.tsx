import { format } from 'date-fns';
import { btnSecondary } from '../../components/ui/classes';
import { ApiError } from '../../api/client';
import { describeError } from '../../lib/errors';
import { useEmailLog, useEmailSettings, useSendTestEmail } from './api';
import { SettingsSection } from './SettingsSection';

export function EmailSection() {
  const settings = useEmailSettings();
  const test = useSendTestEmail();

  return (
    <SettingsSection title="Email">
      {settings.isPending ? <p className="text-sm text-text-muted">Loading...</p> : null}
      {settings.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(settings.error)}
        </p>
      ) : null}
      {settings.data ? (
        <>
          <p className="text-sm">
            {settings.data.configured
              ? `Email is set up. Messages are sent from ${settings.data.from_address ?? 'the configured address'}.`
              : 'Email is not set up. Password reset emails cannot be sent until SMTP is configured on the server.'}
          </p>
          <div className="space-y-2">
            <button
              type="button"
              className={btnSecondary}
              disabled={test.isPending}
              onClick={() => test.mutate()}
            >
              Send test email
            </button>
            <div role="status" className="min-h-5 text-sm text-text-muted">
              {test.isSuccess ? 'Test email sent. Check your inbox.' : null}
            </div>
            {test.isError ? (
              <p role="alert" className="text-sm text-danger">
                {test.error instanceof ApiError && test.error.status === 503
                  ? 'Email is not configured on the server.'
                  : describeError(test.error)}
              </p>
            ) : null}
          </div>
        </>
      ) : null}
      <RecentEmails />
    </SettingsSection>
  );
}

const KIND_LABELS = {
  reminder: 'Reminder',
  password_reset: 'Password reset',
  test: 'Test',
} as const;

function RecentEmails() {
  const log = useEmailLog();
  return (
    <div className="space-y-2 border-t border-border pt-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Recent emails</h3>
        <button
          type="button"
          className={btnSecondary}
          disabled={log.isFetching}
          onClick={() => void log.refetch()}
        >
          Refresh
        </button>
      </div>
      {log.isPending ? <p className="text-sm text-text-muted">Loading...</p> : null}
      {log.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(log.error)}
        </p>
      ) : null}
      {log.data && log.data.length === 0 ? (
        <p className="text-sm text-text-muted">No emails sent yet.</p>
      ) : null}
      {log.data && log.data.length > 0 ? (
        <ul aria-label="Recent emails" className="divide-y divide-border text-sm">
          {log.data.map((entry, index) => (
            <li key={`${entry.created_at}:${index}`} className="py-2">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <time dateTime={entry.created_at} className="text-xs text-text-muted">
                  {format(new Date(entry.created_at), 'd MMM yyyy, HH:mm')}
                </time>
                <span className="text-xs text-text-muted">{KIND_LABELS[entry.kind]}</span>
                <span
                  className={
                    entry.status === 'failed'
                      ? 'text-xs font-medium text-danger'
                      : 'text-xs font-medium'
                  }
                >
                  {entry.status === 'sent' ? 'Sent' : 'Failed'}
                </span>
              </div>
              <div className="break-words">{entry.subject}</div>
              {entry.status === 'failed' && entry.error ? (
                <div className="break-words text-xs text-danger">{entry.error}</div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
