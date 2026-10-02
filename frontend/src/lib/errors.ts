import { ApiError } from '../api/client';

/** "Too many attempts. Try again in N minutes." from a 429's Retry-After (seconds). */
export function lockoutMessage(retryAfterSeconds: number | null): string {
  if (retryAfterSeconds === null) return 'Too many attempts. Try again later.';
  const minutes = Math.max(1, Math.ceil(retryAfterSeconds / 60));
  return `Too many attempts. Try again in ${minutes} ${minutes === 1 ? 'minute' : 'minutes'}.`;
}

/**
 * Turns any failure into a sentence for an inline alert.
 * `overrides` maps HTTP statuses to friendlier text (e.g. 401 -> "Wrong email or password.").
 */
export function describeError(
  error: unknown,
  overrides: Partial<Record<number, string>> = {},
): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return lockoutMessage(error.retryAfter);
    const override = overrides[error.status];
    if (override) return override;
    if (error.status >= 500) return 'Something went wrong on the server. Try again in a moment.';
    if (error.detail) return error.detail;
    return error.title;
  }
  return 'Could not reach the server. Check your connection and try again.';
}
