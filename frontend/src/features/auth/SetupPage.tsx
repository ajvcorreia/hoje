import { useState, type FormEvent } from 'react';
import { Link, Navigate } from 'react-router';
import { btnPrimary, linkClass } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { Spinner } from '../../components/ui/Spinner';
import { useAuthState } from '../../app/useAuthState';
import { ApiError } from '../../api/client';
import { describeError } from '../../lib/errors';
import { MIN_PASSWORD_LENGTH } from '../../lib/password';
import { AuthCard } from './AuthCard';
import { useRegister } from './api';

export function SetupPage() {
  const state = useAuthState();
  const register = useRegister();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  if (state.isPending) return <Spinner />;
  const auth = state.data;
  // Once registered the state flips to authenticated (after the timezone PATCH finished).
  if (auth?.authenticated) return <Navigate to="/" replace />;
  if (auth && !auth.registration_open) return <Navigate to="/login" replace />;

  const longEnough = password.length >= MIN_PASSWORD_LENGTH;
  const serverHint =
    register.error instanceof ApiError && register.error.status === 422
      ? (register.error.detail ?? register.error.title)
      : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!longEnough) return;
    register.mutate({ email: email.trim(), password });
  };

  return (
    <AuthCard title="Create your account">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field
          label="Email"
          name="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          focusOnMount
          required
        />
        <Field
          label="Password"
          name="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          required
          hint={
            <span className={password && !longEnough ? 'text-danger' : undefined}>
              {longEnough
                ? 'Length looks good.'
                : `Use at least ${MIN_PASSWORD_LENGTH} characters.`}
            </span>
          }
          error={serverHint}
        />
        <FormError
          message={register.isError && !serverHint ? describeError(register.error) : null}
        />
        <button
          type="submit"
          className={`${btnPrimary} w-full`}
          disabled={register.isPending || !longEnough}
        >
          Create account
        </button>
        <p className="text-sm">
          <Link to="/login" className={linkClass}>
            I already have an account
          </Link>
        </p>
      </form>
    </AuthCard>
  );
}
