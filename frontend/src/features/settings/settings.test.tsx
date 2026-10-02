import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ME, authState, mockApi, problem, renderApp } from '../../test/utils';

const base = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/settings/email': { configured: true, from_address: 'hoje@example.com' },
};

describe('account settings', () => {
  it('PATCHes ISO weekday numbers when toggling weekend chips', async () => {
    const api = mockApi({
      ...base,
      'GET /api/v1/me': ME,
      'PATCH /api/v1/me': (call) => ({ ...ME, ...(call.body as object) }),
    });
    renderApp('/settings');
    const monday = await screen.findByRole('button', { name: 'Mon' });
    expect(screen.getByRole('button', { name: 'Sat' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(monday);
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/me')).toHaveLength(1));
    expect(api.callsTo('PATCH', '/api/v1/me')[0]?.body).toEqual({ weekend_days: [1, 6, 7] });
    expect(await screen.findByText('Saved')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Sun' }));
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/me')).toHaveLength(2));
    expect(api.callsTo('PATCH', '/api/v1/me')[1]?.body).toEqual({ weekend_days: [1, 6] });
  });

  it('saves the time zone on change and can filter the list', async () => {
    const api = mockApi({
      ...base,
      'GET /api/v1/me': ME,
      'PATCH /api/v1/me': (call) => ({ ...ME, ...(call.body as object) }),
    });
    renderApp('/settings');
    await userEvent.type(await screen.findByLabelText('Filter time zones'), 'utc');
    await userEvent.selectOptions(screen.getByLabelText('Time zone'), 'UTC');
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/me')).toHaveLength(1));
    expect(api.callsTo('PATCH', '/api/v1/me')[0]?.body).toEqual({ timezone: 'UTC' });
  });
});

describe('two-factor setup', () => {
  const QR = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>';
  const CODES = Array.from({ length: 10 }, (_, i) => `abcd${i}-efgh${i}`);

  it('shows the QR as an image, then requires confirming saved recovery codes', async () => {
    const api = mockApi({
      ...base,
      'GET /api/v1/me': ME,
      'POST /api/v1/auth/2fa/setup': {
        otpauth_uri: 'otpauth://totp/Hoje:ana?secret=ABCDEFGHIJKLMNOP',
        secret: 'ABCDEFGHIJKLMNOP',
        qr_svg: QR,
      },
      'POST /api/v1/auth/2fa/enable': { recovery_codes: CODES },
    });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: 'Set up' }));

    const dialog = screen.getByRole('dialog', { name: /two-factor/i });
    await userEvent.type(
      within(dialog).getByLabelText('Confirm your password'),
      'secret-pass{Enter}',
    );
    expect(api.callsTo('POST', '/api/v1/auth/2fa/setup')[0]?.body).toEqual({
      password: 'secret-pass',
    });

    const img = await within(dialog).findByAltText('QR code for your authenticator app');
    const src = img.getAttribute('src') ?? '';
    expect(src.startsWith('data:image/svg+xml;base64,')).toBe(true);
    expect(atob(src.split(',')[1] ?? '')).toBe(QR);
    // The SVG is never injected as markup.
    expect(dialog.querySelector('svg')).toBeNull();
    expect(dialog.querySelector('rect')).toBeNull();
    expect(within(dialog).getByText('ABCD EFGH IJKL MNOP')).toBeInTheDocument();

    await userEvent.type(within(dialog).getByLabelText('Authentication code'), '123456{Enter}');
    expect(api.callsTo('POST', '/api/v1/auth/2fa/enable')[0]?.body).toEqual({ code: '123456' });

    expect(await within(dialog).findByText('abcd0-efgh0')).toBeInTheDocument();
    expect(within(dialog).getAllByRole('listitem')).toHaveLength(10);
    const done = within(dialog).getByRole('button', { name: 'Done' });
    expect(done).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Download .txt' })).toBeInTheDocument();
    await userEvent.click(within(dialog).getByLabelText("I've saved these codes"));
    expect(done).toBeEnabled();
    await userEvent.click(done);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('closes on Escape before the codes are shown', async () => {
    mockApi({ ...base, 'GET /api/v1/me': ME });
    renderApp('/settings');
    const opener = await screen.findByRole('button', { name: 'Set up' });
    await userEvent.click(opener);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(opener).toHaveFocus();
  });

  it('shows a wrong-password error inline', async () => {
    mockApi({
      ...base,
      'GET /api/v1/me': ME,
      'POST /api/v1/auth/2fa/setup': problem(401, 'Wrong password'),
    });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: 'Set up' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Confirm your password'), 'nope{Enter}');
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Wrong password.');
  });

  it('offers regenerate and turn off when enabled', async () => {
    mockApi({
      ...base,
      'GET /api/v1/me': { ...ME, totp_enabled: true },
    });
    renderApp('/settings');
    expect(await screen.findByRole('button', { name: 'Regenerate recovery codes' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Turn off' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Set up' })).not.toBeInTheDocument();
  });
});

describe('email settings', () => {
  it('reports a successful test email', async () => {
    mockApi({
      ...base,
      'GET /api/v1/me': ME,
      'POST /api/v1/settings/email/test': () => Response.json({}, { status: 202 }),
    });
    renderApp('/settings');
    expect(await screen.findByText(/hoje@example\.com/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Send test email' }));
    expect(await screen.findByText(/Test email sent/)).toBeInTheDocument();
  });

  it('reports when SMTP is not configured (503)', async () => {
    mockApi({
      ...base,
      'GET /api/v1/settings/email': { configured: false },
      'GET /api/v1/me': ME,
      'POST /api/v1/settings/email/test': problem(503, 'SMTP not configured'),
    });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: 'Send test email' }));
    expect(await screen.findByText('Email is not configured on the server.')).toBeInTheDocument();
  });
});

describe('session', () => {
  it('logs out from settings and returns to the login page', async () => {
    let state: object = authState();
    mockApi({
      'GET /api/v1/auth/state': () => state,
      'GET /api/v1/me': ME,
      'GET /api/v1/settings/email': { configured: false },
      'POST /api/v1/auth/logout': () => {
        state = { registration_open: false, authenticated: false, stage: null, user: null };
        return new Response(null, { status: 204 });
      },
    });
    const { router } = renderApp('/settings');
    const section = (await screen.findByRole('heading', { name: 'Session' })).closest('section')!;
    await userEvent.click(within(section).getByRole('button', { name: 'Log out' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
  });
});
