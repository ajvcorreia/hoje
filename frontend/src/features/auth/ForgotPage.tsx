import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { btnPrimary, linkClass } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { AuthCard } from './AuthCard';
import { useForgotPassword } from './api';

export function ForgotPage() {
  const forgot = useForgotPassword();
  const [email, setEmail] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    forgot.mutate({ email: email.trim() });
  };

  return (
    <AuthCard title="Reset your password">
      {forgot.isSuccess ? (
        <div className="space-y-4">
          <p role="status" className="text-sm">
            If an account exists for that email, we&apos;ve sent a reset link.
          </p>
          <Link to="/login" className={`${linkClass} text-sm`}>
            Back to log in
          </Link>
        </div>
      ) : (
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
          <FormError message={forgot.isError ? describeError(forgot.error) : null} />
          <button type="submit" className={`${btnPrimary} w-full`} disabled={forgot.isPending}>
            Send reset link
          </button>
          <p className="text-sm">
            <Link to="/login" className={linkClass}>
              Back to log in
            </Link>
          </p>
        </form>
      )}
    </AuthCard>
  );
}
