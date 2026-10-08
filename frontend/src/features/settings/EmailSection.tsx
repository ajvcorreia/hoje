import { useState } from 'react';
import { format } from 'date-fns';
import { btnSecondary, inputClass } from '../../components/ui/classes';
import { ApiError } from '../../api/client';
import { isSummaryTime, useDailySummary } from '../../lib/dailySummary';
import { describeError } from '../../lib/errors';
import { useEmailLog, useEmailSettings, useSendTestDailySummary, useSendTestEmail } from './api';
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
          <DailySummary configured={settings.data.configured} />
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
  security: 'Security',
  daily_summary: 'Daily summary',
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

function DailySummary({ configured }: { configured: boolean }) {
  const summary = useDailySummary();
  const test = useSendTestDailySummary();
  // What is being typed; null once a complete time was saved (or the field lost focus).
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <div className="space-y-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Daily summary</h3>
      <label className="flex min-h-9 items-center gap-2 text-sm font-medium">
        <input
          type="checkbox"
          checked={summary.enabled}
          disabled={!configured && !summary.enabled}
          onChange={(e) => summary.setEnabled(e.target.checked)}
          className="size-4"
        />
        Send me a daily summary email
      </label>
      <div>
        <label htmlFor="daily-summary-time" className="block text-sm font-medium">
          Send at
        </label>
        <input
          id="daily-summary-time"
          type="time"
          value={draft ?? summary.time}
          disabled={!summary.enabled}
          onChange={(e) => {
            setDraft(isSummaryTime(e.target.value) ? null : e.target.value);
            summary.setTime(e.target.value);
          }}
          onBlur={() => setDraft(null)}
          className={`${inputClass} mt-2 sm:max-w-40`}
        />
        <p className="mt-1 text-xs text-text-muted">Time zone: {summary.timezone}</p>
      </div>
      <p className="text-xs text-text-muted">
        {configured
          ? 'The email lists what changed in your calendar since the last summary, today’s events, today’s birthdays and holidays, and tomorrow’s events. Days with nothing to report are skipped.'
          : 'Email is not set up on this server, so daily summaries cannot be sent yet.'}
      </p>
      {summary.error ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(summary.error)}
        </p>
      ) : null}
      <div className="space-y-2">
        <button
          type="button"
          className={btnSecondary}
          disabled={!configured || test.isPending}
          onClick={() => test.mutate()}
        >
          Send a test summary
        </button>
        <div role="status" className="min-h-5 text-sm text-text-muted">
          {test.isSuccess ? 'Test summary sent. Check your inbox.' : null}
        </div>
        {test.isError ? (
          <p role="alert" className="text-sm text-danger">
            {test.error instanceof ApiError && test.error.status === 503
              ? 'Email is not configured on the server.'
              : describeError(test.error)}
          </p>
        ) : null}
      </div>
    </div>
  );
}
