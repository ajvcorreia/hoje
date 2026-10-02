import { useState, type FormEvent } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router';
import { btnPrimary, linkClass } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { Spinner } from '../../components/ui/Spinner';
import { useAuthState } from '../../app/useAuthState';
import { describeError } from '../../lib/errors';
import { safeNext } from '../../lib/safeNext';
import { AuthCard } from './AuthCard';
import { useLogin, useLoginMfa } from './api';

function CodeStep() {
  const mfa = useLoginMfa();
  const [code, setCode] = useState('');
  const [recovery, setRecovery] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    mfa.mutate({ code: code.trim() });
  };

  return (
    <AuthCard title="Two-factor authentication">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field
          key={recovery ? 'recovery' : 'totp'}
          label={recovery ? 'Recovery code' : 'Authentication code'}
          name="code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoComplete="one-time-code"
          inputMode={recovery ? 'text' : 'numeric'}
          placeholder={recovery ? 'xxxxx-xxxxx' : '123456'}
          focusOnMount
          required
        />
        <FormError
          message={
            mfa.isError
              ? describeError(mfa.error, { 401: 'That code did not work. Try again.' })
              : null
          }
        />
        <button type="submit" className={`${btnPrimary} w-full`} disabled={mfa.isPending}>
          Verify
        </button>
        <button
          type="button"
          className={`${linkClass} text-sm`}
          onClick={() => {
            setRecovery((r) => !r);
            setCode('');
            mfa.reset();
          }}
        >
          {recovery ? 'Use an authentication code' : 'Use a recovery code'}
        </button>
      </form>
    </AuthCard>
  );
}

export function LoginPage() {
  const state = useAuthState();
  const login = useLogin();
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  if (state.isPending) return <Spinner />;
  const auth = state.data;
  if (auth?.stage === 'mfa_pending') return <CodeStep />;
  if (auth?.authenticated) return <Navigate to={next} replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate({ email: email.trim(), password });
  };

  return (
    <AuthCard title="Log in">
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
          autoComplete="current-password"
          required
        />
        <FormError
          message={
            login.isError ? describeError(login.error, { 401: 'Wrong email or password.' }) : null
          }
        />
        <button type="submit" className={`${btnPrimary} w-full`} disabled={login.isPending}>
          Log in
        </button>
        <div className="flex justify-between text-sm">
          <Link to="/forgot" className={linkClass}>
            Forgot password?
          </Link>
          {auth?.registration_open ? (
            <Link to="/setup" className={linkClass}>
              Create account
            </Link>
          ) : null}
        </div>
      </form>
    </AuthCard>
  );
}
