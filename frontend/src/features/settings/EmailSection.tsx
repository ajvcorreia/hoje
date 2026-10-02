import { btnSecondary } from '../../components/ui/classes';
import { ApiError } from '../../api/client';
import { describeError } from '../../lib/errors';
import { useEmailSettings, useSendTestEmail } from './api';
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
    </SettingsSection>
  );
}
