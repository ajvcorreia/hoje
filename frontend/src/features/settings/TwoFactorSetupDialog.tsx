import { useState, type FormEvent } from 'react';
import { btnPrimary, btnSecondary } from '../../components/ui/classes';
import { Dialog } from '../../components/ui/Dialog';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { groupSecret, svgDataUri } from '../../lib/twoFactor';
import { useTwoFactorEnable, useTwoFactorSetup } from './api';
import { CopyButton, RecoveryCodesPanel } from './RecoveryCodesPanel';

type Step =
  | { name: 'password' }
  | { name: 'scan'; qrSvg: string; secret: string }
  | { name: 'codes'; codes: string[] };

interface Props {
  onClose: () => void;
  /** Called once the user has confirmed saving the codes. */
  onFinished: () => void;
}

export function TwoFactorSetupDialog({ onClose, onFinished }: Props) {
  const setup = useTwoFactorSetup();
  const enable = useTwoFactorEnable();
  const [step, setStep] = useState<Step>({ name: 'password' });
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');

  const submitPassword = (event: FormEvent) => {
    event.preventDefault();
    setup.mutate(
      { password },
      {
        onSuccess: (res) => {
          setPassword('');
          setStep({ name: 'scan', qrSvg: res.qr_svg, secret: res.secret });
        },
      },
    );
  };

  const submitCode = (event: FormEvent) => {
    event.preventDefault();
    enable.mutate(
      { code: code.trim() },
      { onSuccess: (res) => setStep({ name: 'codes', codes: res.recovery_codes }) },
    );
  };

  return (
    <Dialog
      title="Set up two-factor authentication"
      onClose={onClose}
      dismissible={step.name !== 'codes'}
    >
      {step.name === 'password' ? (
        <form onSubmit={submitPassword} className="space-y-4" noValidate>
          <Field
            label="Confirm your password"
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-autofocus
            required
          />
          <FormError
            message={setup.isError ? describeError(setup.error, { 401: 'Wrong password.' }) : null}
          />
          <div className="flex gap-2">
            <button type="submit" className={btnPrimary} disabled={setup.isPending}>
              Continue
            </button>
            <button type="button" className={btnSecondary} onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      {step.name === 'scan' ? (
        <form onSubmit={submitCode} className="space-y-4" noValidate>
          <p className="text-sm">
            Scan this QR code with your authenticator app, then enter the 6-digit code it shows.
          </p>
          <img
            src={svgDataUri(step.qrSvg)}
            alt="QR code for your authenticator app"
            className="mx-auto size-48 rounded-md bg-white p-2"
          />
          <div>
            <p className="text-sm font-medium">Can&apos;t scan? Enter this key instead</p>
            <div className="mt-1 flex items-center gap-2">
              <code className="flex-1 break-all rounded-md border border-border bg-surface-muted px-2 py-1 font-mono text-sm">
                {groupSecret(step.secret)}
              </code>
              <CopyButton text={step.secret} />
            </div>
          </div>
          <Field
            label="Authentication code"
            name="code"
            autoComplete="one-time-code"
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            data-autofocus
            required
          />
          <FormError
            message={
              enable.isError
                ? describeError(enable.error, { 401: 'That code did not work. Try again.' })
                : null
            }
          />
          <div className="flex gap-2">
            <button type="submit" className={btnPrimary} disabled={enable.isPending}>
              Verify
            </button>
            <button type="button" className={btnSecondary} onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      {step.name === 'codes' ? <RecoveryCodesPanel codes={step.codes} onDone={onFinished} /> : null}
    </Dialog>
  );
}
