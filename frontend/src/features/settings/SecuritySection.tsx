import { useState, type FormEvent } from 'react';
import { btnPrimary, btnSecondary } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { ApiError } from '../../api/client';
import { describeError } from '../../lib/errors';
import { MIN_PASSWORD_LENGTH } from '../../lib/password';
import { useChangePassword, useMe, useRefreshMe } from './api';
import { SettingsSection } from './SettingsSection';
import { TwoFactorManageDialog } from './TwoFactorManageDialog';
import { TwoFactorSetupDialog } from './TwoFactorSetupDialog';

function ChangePasswordForm() {
  const change = useChangePassword();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [mismatch, setMismatch] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (next !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent('');
          setNext('');
          setConfirm('');
        },
      },
    );
  };

  const serverHint =
    change.error instanceof ApiError && change.error.status === 422
      ? (change.error.detail ?? change.error.title)
      : null;

  return (
    <form onSubmit={submit} className="space-y-3" noValidate aria-label="Change password">
      <h3 className="text-sm font-semibold">Change password</h3>
      <Field
        label="Current password"
        type="password"
        name="current_password"
        autoComplete="current-password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        required
      />
      <Field
        label="New password"
        type="password"
        name="new_password"
        autoComplete="new-password"
        value={next}
        onChange={(e) => setNext(e.target.value)}
        hint={`Use at least ${MIN_PASSWORD_LENGTH} characters.`}
        error={serverHint}
        required
      />
      <Field
        label="Confirm new password"
        type="password"
        name="confirm_password"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        required
      />
      <FormError
        message={
          mismatch
            ? 'The passwords do not match.'
            : change.isError && !serverHint
              ? describeError(change.error, { 401: 'Your current password is wrong.' })
              : null
        }
      />
      <div className="flex items-center gap-3">
        <button type="submit" className={btnPrimary} disabled={change.isPending}>
          Change password
        </button>
        <span role="status" className="text-sm text-text-muted">
          {change.isSuccess ? 'Password changed' : null}
        </span>
      </div>
    </form>
  );
}

type Dialogs = null | 'setup' | 'regenerate' | 'disable';

function TwoFactor() {
  const me = useMe();
  const refresh = useRefreshMe();
  const [dialog, setDialog] = useState<Dialogs>(null);
  const enabled = me.data?.totp_enabled ?? false;

  const close = () => setDialog(null);
  const finished = () => {
    setDialog(null);
    void refresh();
  };

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Two-factor authentication</h3>
      {me.isPending ? <p className="text-sm text-text-muted">Loading...</p> : null}
      {me.data ? (
        <>
          <p className="text-sm">
            {enabled
              ? 'Two-factor authentication is on.'
              : 'Two-factor authentication is off. Add a second step to protect your account.'}
          </p>
          <div className="flex flex-wrap gap-2">
            {enabled ? (
              <>
                <button
                  type="button"
                  className={btnSecondary}
                  onClick={() => setDialog('regenerate')}
                >
                  Regenerate recovery codes
                </button>
                <button type="button" className={btnSecondary} onClick={() => setDialog('disable')}>
                  Turn off
                </button>
              </>
            ) : (
              <button type="button" className={btnPrimary} onClick={() => setDialog('setup')}>
                Set up
              </button>
            )}
          </div>
        </>
      ) : null}
      {dialog === 'setup' ? <TwoFactorSetupDialog onClose={close} onFinished={finished} /> : null}
      {dialog === 'regenerate' || dialog === 'disable' ? (
        <TwoFactorManageDialog mode={dialog} onClose={close} onFinished={finished} />
      ) : null}
    </div>
  );
}

export function SecuritySection() {
  return (
    <SettingsSection title="Security">
      <ChangePasswordForm />
      <hr className="border-border" />
      <TwoFactor />
    </SettingsSection>
  );
}
