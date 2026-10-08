import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { ME, authState, mockApi, problem, renderApp } from '../../test/utils';

const base = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/settings/email': { configured: true, from_address: 'hoje@example.com' },
  'GET /api/v1/settings/email/log': [],
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

  it('lists recent emails with the error of failed ones and can refresh', async () => {
    let rows = [
      {
        created_at: '2026-10-02T12:30:00Z',
        kind: 'reminder',
        subject: 'Reminder: Dentist · Fri 9 Oct',
        status: 'sent',
        error: null,
      },
      {
        created_at: '2026-10-02T12:00:00Z',
        kind: 'test',
        subject: 'Hoje test email',
        status: 'failed',
        error: 'SMTPConnectError: refused',
      },
    ];
    const api = mockApi({
      ...base,
      'GET /api/v1/me': ME,
      'GET /api/v1/settings/email/log': () => rows,
    });
    renderApp('/settings');
    const list = await screen.findByRole('list', { name: 'Recent emails' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getByText('Reminder: Dentist · Fri 9 Oct')).toBeVisible();
    expect(within(list).getByText('SMTPConnectError: refused')).toBeVisible();
    expect(api.callsTo('GET', '/api/v1/settings/email/log')[0]?.search).toBe('?limit=20');
    rows = rows.slice(0, 1);
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(within(list).getAllByRole('listitem')).toHaveLength(1));
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

describe('appearance settings', () => {
  afterEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-text-size');
  });

  it('applies and stores the text size, and has no multi-day names setting', async () => {
    mockApi({ ...base, 'GET /api/v1/me': ME });
    renderApp('/settings');
    const select = await screen.findByLabelText('Text size');
    expect(select).toHaveValue('default');
    expect(screen.queryByLabelText('Multi-day event names')).not.toBeInTheDocument();
    await userEvent.selectOptions(select, 'Large');
    expect(document.documentElement).toHaveAttribute('data-text-size', 'large');
    expect(window.localStorage.getItem('hoje.textSize')).toBe('large');
  });

  it('toggles week numbers', async () => {
    mockApi({ ...base, 'GET /api/v1/me': ME });
    renderApp('/settings');
    const box = await screen.findByLabelText('Show week numbers');
    expect(box).toBeChecked();
    await userEvent.click(box);
    expect(box).not.toBeChecked();
    expect(window.localStorage.getItem('hoje.weekNumbers')).toBe('off');
  });
});

describe('events per day setting', () => {
  it('defaults to 2 and saves a choice on the user', async () => {
    let me = { ...ME, max_events_per_day: 2 };
    const api = mockApi({
      ...base,
      'GET /api/v1/auth/state': () => authState({ user: me }),
      'GET /api/v1/me': () => me,
      'PATCH /api/v1/me': (call) => {
        me = { ...me, ...(call.body as object) };
        return me;
      },
    });
    renderApp('/settings');
    const select = await screen.findByLabelText('Events shown per day');
    expect(select).toHaveValue('2');
    await userEvent.selectOptions(select, '4');
    expect(select).toHaveValue('4');
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/me')).toHaveLength(1));
    expect(api.callsTo('PATCH', '/api/v1/me')[0]?.body).toEqual({ max_events_per_day: 4 });
    expect(window.localStorage.getItem('hoje.maxEventsPerDay')).toBeNull();
    await waitFor(() => expect(select).toHaveValue('4'));
  });

  it('shows the value stored on the user', async () => {
    mockApi({
      ...base,
      'GET /api/v1/auth/state': authState({ user: { ...ME, max_events_per_day: 5 } }),
      'GET /api/v1/me': { ...ME, max_events_per_day: 5 },
    });
    renderApp('/settings');
    expect(await screen.findByLabelText('Events shown per day')).toHaveValue('5');
  });
});

describe('strike through past days setting', () => {
  it('is off by default and persists when switched on', async () => {
    window.localStorage.removeItem('hoje.strikePast');
    mockApi({ ...base, 'GET /api/v1/me': ME });
    renderApp('/settings');
    const box = await screen.findByLabelText('Strike through past days');
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    expect(box).toBeChecked();
    expect(window.localStorage.getItem('hoje.strikePast')).toBe('on');
    await userEvent.click(box);
  });
});

describe('vertical event text size setting', () => {
  it('defaults to 12 px and saves a choice on the user', async () => {
    let me = { ...ME, vertical_text_size: 12 };
    const api = mockApi({
      ...base,
      'GET /api/v1/auth/state': () => authState({ user: me }),
      'GET /api/v1/me': () => me,
      'PATCH /api/v1/me': (call) => {
        me = { ...me, ...(call.body as object) };
        return me;
      },
    });
    renderApp('/settings');
    const select = await screen.findByLabelText('Vertical event text size');
    expect(select).toHaveValue('12');
    expect(
      screen.getByText("Shrinks automatically when the name does not fit the event's height"),
    ).toBeInTheDocument();
    await userEvent.selectOptions(select, '24');
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/me')).toHaveLength(1));
    expect(api.callsTo('PATCH', '/api/v1/me')[0]?.body).toEqual({ vertical_text_size: 24 });
    await waitFor(() => expect(select).toHaveValue('24'));
  });
});

describe('daily summary email setting', () => {
  const withSummary = (over: object = {}) => ({
    ...ME,
    daily_summary_enabled: false,
    daily_summary_time: '07:00',
    ...over,
  });

  function setup(extra: Record<string, unknown> = {}, emailConfigured = true) {
    let me = withSummary();
    const api = mockApi({
      ...base,
      'GET /api/v1/settings/email': {
        configured: emailConfigured,
        from_address: 'hoje@example.com',
      },
      'GET /api/v1/auth/state': () => authState({ user: me }),
      'GET /api/v1/me': () => me,
      'PATCH /api/v1/me': (call) => {
        me = { ...me, ...(call.body as object) };
        return me;
      },
      ...extra,
    });
    return api;
  }

  it('is off by default with the time disabled, the zone shown and the contents explained', async () => {
    setup();
    renderApp('/settings');
    const toggle = await screen.findByRole('checkbox', { name: 'Send me a daily summary email' });
    expect(toggle).not.toBeChecked();
    expect(screen.getByLabelText('Send at')).toBeDisabled();
    expect(screen.getByLabelText('Send at')).toHaveValue('07:00');
    expect(screen.getByText('Time zone: Europe/Lisbon')).toBeInTheDocument();
    expect(screen.getByText(/Days with nothing to report are skipped/)).toBeInTheDocument();
  });

  it('PATCHes the switch and then the time as HH:MM', async () => {
    const api = setup();
    renderApp('/settings');
    const toggle = await screen.findByRole('checkbox', { name: 'Send me a daily summary email' });
    await userEvent.click(toggle);
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/me')).toHaveLength(1));
    expect(api.callsTo('PATCH', '/api/v1/me')[0]?.body).toEqual({ daily_summary_enabled: true });
    await waitFor(() => expect(toggle).toBeChecked());

    const time = screen.getByLabelText('Send at');
    await waitFor(() => expect(time).toBeEnabled());
    fireEvent.change(time, { target: { value: '18:45' } });
    await waitFor(() => expect(api.callsTo('PATCH', '/api/v1/me')).toHaveLength(2));
    expect(api.callsTo('PATCH', '/api/v1/me')[1]?.body).toEqual({ daily_summary_time: '18:45' });
    await waitFor(() => expect(time).toHaveValue('18:45'));
  });

  it('does not send an incomplete time', async () => {
    const api = setup();
    renderApp('/settings');
    await userEvent.click(
      await screen.findByRole('checkbox', { name: 'Send me a daily summary email' }),
    );
    const time = screen.getByLabelText('Send at');
    await waitFor(() => expect(time).toBeEnabled());
    fireEvent.change(time, { target: { value: '' } });
    expect(api.callsTo('PATCH', '/api/v1/me')).toHaveLength(1);
  });

  it('sends a test summary and reports it', async () => {
    const api = setup({
      'POST /api/v1/settings/email/daily-summary/test': () => Response.json({}, { status: 202 }),
    });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: 'Send a test summary' }));
    expect(await screen.findByText(/Test summary sent/)).toBeInTheDocument();
    expect(api.callsTo('POST', '/api/v1/settings/email/daily-summary/test')).toHaveLength(1);
  });

  it('reports a failed test summary', async () => {
    setup({
      'POST /api/v1/settings/email/daily-summary/test': problem(502, 'mail server down'),
    });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: 'Send a test summary' }));
    expect(await screen.findByText(/Something went wrong on the server/)).toBeInTheDocument();
  });

  it('is disabled with an explanation when email is not configured on the server', async () => {
    setup({}, false);
    renderApp('/settings');
    const toggle = await screen.findByRole('checkbox', { name: 'Send me a daily summary email' });
    expect(toggle).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Send a test summary' })).toBeDisabled();
    expect(screen.getByText(/daily summaries cannot be sent yet/)).toBeInTheDocument();
  });

  it('labels daily summary rows in Recent emails', async () => {
    setup({
      'GET /api/v1/settings/email/log': () => [
        {
          created_at: '2026-10-08T06:00:00Z',
          kind: 'daily_summary',
          subject: 'Hoje — Thursday 8 October: 2 events today',
          status: 'sent',
          error: null,
        },
      ],
    });
    renderApp('/settings');
    const list = await screen.findByRole('list', { name: 'Recent emails' });
    expect(within(list).getByText('Daily summary')).toBeVisible();
  });
});
