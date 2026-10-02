import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { ApiError } from '../../api/client';
import { btnPrimary, linkClass } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { MIN_PASSWORD_LENGTH } from '../../lib/password';
import { AuthCard } from './AuthCard';
import { useResetPassword } from './api';

function readTokenFromHash(): string {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  return params.get('token') ?? '';
}

export function ResetPage() {
  // Read once; the fragment is then removed so the token does not linger in the address bar.
  const [token] = useState(readTokenFromHash);
  const reset = useResetPassword();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [mismatch, setMismatch] = useState(false);

  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(
        window.history.state,
        '',
        window.location.pathname + window.location.search,
      );
    }
  }, []);

  const invalidLink = (
    <div className="space-y-4">
      <p role="alert" className="text-sm text-danger">
        This reset link is missing, invalid or has expired.
      </p>
      <Link to="/forgot" className={`${linkClass} text-sm`}>
        Request a new link
      </Link>
    </div>
  );

  if (!token) return <AuthCard title="Set a new password">{invalidLink}</AuthCard>;

  if (reset.isSuccess) {
    return (
      <AuthCard title="Password updated">
        <div className="space-y-4">
          <p role="status" className="text-sm">
            Your password has been changed.
          </p>
          <Link to="/login" className={`${btnPrimary} w-full`}>
            Log in
          </Link>
        </div>
      </AuthCard>
    );
  }

  if (reset.error instanceof ApiError && reset.error.status === 400) {
    return <AuthCard title="Set a new password">{invalidLink}</AuthCard>;
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (password !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    reset.mutate({ token, new_password: password });
  };

  const serverHint =
    reset.error instanceof ApiError && reset.error.status === 422
      ? (reset.error.detail ?? reset.error.title)
      : null;

  return (
    <AuthCard title="Set a new password">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field
          label="New password"
          name="new_password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          focusOnMount
          required
          hint={`Use at least ${MIN_PASSWORD_LENGTH} characters.`}
          error={serverHint}
        />
        <Field
          label="Confirm new password"
          name="confirm"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
          required
        />
        <FormError
          message={
            mismatch
              ? 'The passwords do not match.'
              : reset.isError && !serverHint
                ? describeError(reset.error)
                : null
          }
        />
        <button type="submit" className={`${btnPrimary} w-full`} disabled={reset.isPending}>
          Set new password
        </button>
      </form>
    </AuthCard>
  );
}
