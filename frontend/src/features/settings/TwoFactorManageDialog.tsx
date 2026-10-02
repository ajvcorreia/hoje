import { useState, type FormEvent } from 'react';
import { btnDanger, btnPrimary, btnSecondary } from '../../components/ui/classes';
import { Dialog } from '../../components/ui/Dialog';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { useRegenerateRecoveryCodes, useTwoFactorDisable } from './api';
import { RecoveryCodesPanel } from './RecoveryCodesPanel';

interface Props {
  mode: 'regenerate' | 'disable';
  onClose: () => void;
  /** Called after 2FA was turned off, or new codes were acknowledged. */
  onFinished: () => void;
}

export function TwoFactorManageDialog({ mode, onClose, onFinished }: Props) {
  const disable = useTwoFactorDisable();
  const regenerate = useRegenerateRecoveryCodes();
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const action = mode === 'disable' ? disable : regenerate;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const body = { password, code: code.trim() };
    if (mode === 'disable') {
      disable.mutate(body, { onSuccess: onFinished });
    } else {
      regenerate.mutate(body, { onSuccess: (res) => setCodes(res.recovery_codes) });
    }
  };

  const title =
    mode === 'disable' ? 'Turn off two-factor authentication' : 'Regenerate recovery codes';

  return (
    <Dialog title={title} onClose={onClose} dismissible={codes === null}>
      {codes ? (
        <RecoveryCodesPanel codes={codes} onDone={onFinished} />
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          <p className="text-sm text-text-muted">
            {mode === 'disable'
              ? 'Enter your password and a current code to turn it off.'
              : 'Your old recovery codes will stop working.'}
          </p>
          <Field
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-autofocus
            required
          />
          <Field
            label="Authentication code"
            name="code"
            autoComplete="one-time-code"
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            hint="A 6-digit code or a recovery code."
            required
          />
          <FormError
            message={
              action.isError
                ? describeError(action.error, { 401: 'Wrong password or code.' })
                : null
            }
          />
          <div className="flex gap-2">
            <button
              type="submit"
              className={mode === 'disable' ? btnDanger : btnPrimary}
              disabled={action.isPending}
            >
              {mode === 'disable' ? 'Turn off' : 'Regenerate'}
            </button>
            <button type="button" className={btnSecondary} onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
