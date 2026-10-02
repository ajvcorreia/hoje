import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ME, authState, mockApi, problem, renderApp } from '../test/utils';

const authed = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/me': ME,
  'GET /api/v1/settings/email': { configured: false, from_address: null },
};

describe('AppShell', () => {
  it('shows the app name and both nav items', async () => {
    mockApi(authed);
    renderApp();
    expect(await screen.findByRole('banner')).toHaveTextContent('Hoje');
    const desktop = screen.getByRole('navigation', { name: 'Main' });
    const mobile = screen.getByRole('navigation', { name: 'Main (mobile)' });
    for (const nav of [desktop, mobile]) {
      expect(within(nav).getByRole('link', { name: 'Calendar' })).toBeInTheDocument();
      expect(within(nav).getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    }
    expect(screen.getByRole('heading', { name: 'Calendar' })).toBeInTheDocument();
  });

  it('has no API notice when the auth state loads fine', async () => {
    mockApi(authed);
    renderApp();
    await screen.findByRole('banner');
    expect(screen.queryByText('API not ready')).not.toBeInTheDocument();
  });

  it('shows a non-blocking notice while the API is not ready', async () => {
    mockApi({ 'GET /api/v1/auth/state': problem(501) });
    renderApp();
    expect(await screen.findByText('API not ready')).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('has a skip link to the main landmark', async () => {
    mockApi(authed);
    renderApp();
    expect(await screen.findByRole('link', { name: 'Skip to content' })).toHaveAttribute(
      'href',
      '#main',
    );
  });

  it('offers Settings and Log out from the user menu', async () => {
    mockApi(authed);
    renderApp();
    await userEvent.click(await screen.findByRole('button', { name: /account menu/i }));
    const menu = screen.getByRole('menu');
    expect(within(menu).getByRole('menuitem', { name: 'Settings' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'Log out' })).toBeInTheDocument();
  });

  it('changes the theme from settings', async () => {
    mockApi(authed);
    renderApp('/settings');
    await userEvent.selectOptions(await screen.findByLabelText('Theme'), 'dark');
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(window.localStorage.getItem('hoje.theme')).toBe('dark');
  });
});
