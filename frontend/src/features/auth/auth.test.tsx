import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ME, LOGGED_OUT, authState, mockApi, problem, renderApp } from '../../test/utils';

describe('route guard', () => {
  it('sends unauthenticated visitors to /login with next', async () => {
    mockApi({ 'GET /api/v1/auth/state': LOGGED_OUT });
    const { router } = renderApp('/settings');
    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
    expect(router.state.location.search).toBe('?next=%2Fsettings');
  });

  it('sends everyone to /setup while registration is open', async () => {
    mockApi({ 'GET /api/v1/auth/state': { ...LOGGED_OUT, registration_open: true } });
    const { router } = renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Create your account' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/setup');
  });

  it('shows the code step when a second factor is pending', async () => {
    mockApi({
      'GET /api/v1/auth/state': { ...LOGGED_OUT, stage: 'mfa_pending' },
    });
    const { router } = renderApp('/settings');
    expect(await screen.findByLabelText('Authentication code')).toHaveAttribute(
      'autocomplete',
      'one-time-code',
    );
    expect(router.state.location.pathname).toBe('/login');
  });

  it('only links to /setup from /login when registration is open', async () => {
    mockApi({ 'GET /api/v1/auth/state': LOGGED_OUT });
    renderApp('/login');
    await screen.findByRole('heading', { name: 'Log in' });
    expect(screen.queryByRole('link', { name: 'Create account' })).not.toBeInTheDocument();
  });
});

describe('next parameter', () => {
  it.each(['//evil.com', 'https://evil.com', 'javascript:alert(1)'])(
    'ignores the unsafe value %s',
    async (unsafe) => {
      mockApi({
        'GET /api/v1/auth/state': authState(),
        'GET /api/v1/me': ME,
      });
      const { router } = renderApp(`/login?next=${encodeURIComponent(unsafe)}`);
      await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    },
  );

  it('follows a safe relative next after login', async () => {
    let state: object = LOGGED_OUT;
    mockApi({
      'GET /api/v1/auth/state': () => state,
      'POST /api/v1/auth/login': () => {
        state = authState();
        return { status: 'ok' };
      },
      'GET /api/v1/me': ME,
      'GET /api/v1/settings/email': { configured: false },
    });
    const { router } = renderApp('/login?next=%2Fsettings');
    await userEvent.type(await screen.findByLabelText('Email'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse{Enter}');
    await waitFor(() => expect(router.state.location.pathname).toBe('/settings'));
  });
});

describe('login', () => {
  it('logs in and goes to the calendar', async () => {
    let state: object = LOGGED_OUT;
    const api = mockApi({
      'GET /api/v1/auth/state': () => state,
      'POST /api/v1/auth/login': () => {
        state = authState();
        return { status: 'ok' };
      },
    });
    const { router } = renderApp('/login');
    const email = await screen.findByLabelText('Email');
    expect(email).toHaveFocus();
    expect(email).toHaveAttribute('autocomplete', 'email');
    expect(screen.getByLabelText('Password')).toHaveAttribute('autocomplete', 'current-password');
    await userEvent.type(email, 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'hunter2hunter2{Enter}');
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(api.callsTo('POST', '/api/v1/auth/login')[0]?.body).toEqual({
      email: 'ana@example.com',
      password: 'hunter2hunter2',
    });
  });

  it('switches to the code step, with a recovery code toggle', async () => {
    let state: object = LOGGED_OUT;
    const api = mockApi({
      'GET /api/v1/auth/state': () => state,
      'POST /api/v1/auth/login': () => {
        state = { ...LOGGED_OUT, stage: 'mfa_pending' };
        return { status: 'mfa_required' };
      },
      'POST /api/v1/auth/login/mfa': () => {
        state = authState();
        return { status: 'ok' };
      },
    });
    const { router } = renderApp('/login');
    await userEvent.type(await screen.findByLabelText('Email'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'hunter2hunter2{Enter}');

    const code = await screen.findByLabelText('Authentication code');
    expect(code).toHaveAttribute('inputmode', 'numeric');
    await userEvent.click(screen.getByRole('button', { name: 'Use a recovery code' }));
    const recovery = screen.getByLabelText('Recovery code');
    expect(recovery).toHaveAttribute('inputmode', 'text');
    await userEvent.type(recovery, 'abcde-fghij{Enter}');

    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(api.callsTo('POST', '/api/v1/auth/login/mfa')[0]?.body).toEqual({ code: 'abcde-fghij' });
  });

  it('shows an inline message for wrong credentials', async () => {
    mockApi({
      'GET /api/v1/auth/state': LOGGED_OUT,
      'POST /api/v1/auth/login': problem(401, 'Invalid credentials'),
    });
    renderApp('/login');
    await userEvent.type(await screen.findByLabelText('Email'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'nope{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong email or password.');
  });

  it('shows the lockout time in minutes from Retry-After', async () => {
    mockApi({
      'GET /api/v1/auth/state': LOGGED_OUT,
      'POST /api/v1/auth/login': problem(429, 'slow down', { 'Retry-After': '300' }),
    });
    renderApp('/login');
    await userEvent.type(await screen.findByLabelText('Email'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'nope{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Too many attempts. Try again in 5 minutes.',
    );
  });
});

describe('setup', () => {
  it('registers, sets the time zone and lands on the calendar', async () => {
    let state: object = { ...LOGGED_OUT, registration_open: true };
    const api = mockApi({
      'GET /api/v1/auth/state': () => state,
      'POST /api/v1/auth/register': () => {
        state = authState();
        return Response.json(ME, { status: 201 });
      },
      'PATCH /api/v1/me': ME,
    });
    const { router } = renderApp('/setup');
    const button = await screen.findByRole('button', { name: 'Create account' });
    await userEvent.type(screen.getByLabelText('Email'), 'ana@example.com');
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Password'), 'a long enough pass{Enter}');
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    const patch = api.callsTo('PATCH', '/api/v1/me')[0]?.body as { timezone: string } | undefined;
    expect(patch?.timezone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
  });

  it('hides the setup token field unless the server requires one', async () => {
    mockApi({ 'GET /api/v1/auth/state': { ...LOGGED_OUT, registration_open: true } });
    renderApp('/setup');
    await screen.findByRole('button', { name: 'Create account' });
    expect(screen.queryByLabelText('Setup token')).not.toBeInTheDocument();
  });

  it('sends the setup token and shows the 403 message', async () => {
    const api = mockApi({
      'GET /api/v1/auth/state': {
        ...LOGGED_OUT,
        registration_open: true,
        setup_token_required: true,
      },
      'POST /api/v1/auth/register': problem(403, 'A valid setup token is required'),
    });
    renderApp('/setup');
    const token = await screen.findByLabelText('Setup token');
    expect(token).toHaveAttribute('autocomplete', 'off');
    await userEvent.type(screen.getByLabelText('Email'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'a long enough pass');
    expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled();
    await userEvent.type(token, 'my-setup-token{Enter}');
    expect(await screen.findByText('A valid setup token is required')).toBeInTheDocument();
    const body = api.callsTo('POST', '/api/v1/auth/register')[0]?.body as
      { setup_token?: string } | undefined;
    expect(body?.setup_token).toBe('my-setup-token');
  });

  it('shows the server strength feedback under the field', async () => {
    mockApi({
      'GET /api/v1/auth/state': { ...LOGGED_OUT, registration_open: true },
      'POST /api/v1/auth/register': problem(422, 'This is a very common password.'),
    });
    renderApp('/setup');
    await userEvent.type(await screen.findByLabelText('Email'), 'ana@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'password1234{Enter}');
    expect(await screen.findByText('This is a very common password.')).toBeInTheDocument();
  });
});

describe('forgot password', () => {
  it('always shows the same confirmation', async () => {
    mockApi({
      'GET /api/v1/auth/state': LOGGED_OUT,
      'POST /api/v1/auth/password/forgot': () => Response.json({}, { status: 202 }),
    });
    renderApp('/forgot');
    await userEvent.type(await screen.findByLabelText('Email'), 'nobody@example.com{Enter}');
    expect(await screen.findByRole('status')).toHaveTextContent(
      "If an account exists for that email, we've sent a reset link.",
    );
  });
});

describe('reset password', () => {
  it('reads the token from the fragment and clears it from the address bar', async () => {
    window.history.replaceState(null, '', '/reset#token=tok-123');
    const api = mockApi({
      'GET /api/v1/auth/state': LOGGED_OUT,
      'POST /api/v1/auth/password/reset': null,
    });
    renderApp('/reset');
    await userEvent.type(await screen.findByLabelText('New password'), 'a brand new password');
    await userEvent.type(
      screen.getByLabelText('Confirm new password'),
      'a brand new password{Enter}',
    );
    expect(await screen.findByText('Your password has been changed.')).toBeInTheDocument();
    expect(api.callsTo('POST', '/api/v1/auth/password/reset')[0]?.body).toEqual({
      token: 'tok-123',
      new_password: 'a brand new password',
    });
    expect(window.location.hash).toBe('');
    expect(screen.getByRole('link', { name: 'Log in' })).toBeInTheDocument();
  });

  it('explains a missing token and links to a new request', async () => {
    window.history.replaceState(null, '', '/reset');
    mockApi({ 'GET /api/v1/auth/state': LOGGED_OUT });
    renderApp('/reset');
    expect(await screen.findByRole('alert')).toHaveTextContent(/missing, invalid or has expired/);
    expect(screen.getByRole('link', { name: 'Request a new link' })).toHaveAttribute(
      'href',
      '/forgot',
    );
  });

  it('shows the same friendly error when the server rejects the token', async () => {
    window.history.replaceState(null, '', '/reset#token=bad');
    mockApi({ 'POST /api/v1/auth/password/reset': problem(400, 'Invalid token') });
    renderApp('/reset');
    await userEvent.type(await screen.findByLabelText('New password'), 'a brand new password');
    await userEvent.type(
      screen.getByLabelText('Confirm new password'),
      'a brand new password{Enter}',
    );
    expect(await screen.findByRole('link', { name: 'Request a new link' })).toBeInTheDocument();
  });
});
