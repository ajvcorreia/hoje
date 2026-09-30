import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createQueryClient } from './queryClient';
import { routes } from './router';

function renderApp(path = '/') {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  // Auth endpoints are stubs (501) for now.
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      Response.json(
        { title: 'Not Implemented', status: 501 },
        { status: 501, headers: { 'content-type': 'application/problem+json' } },
      ),
    ),
  );
});

describe('AppShell', () => {
  it('shows the app name and both nav items', () => {
    renderApp();
    expect(within(screen.getByRole('banner')).getByText('Hoje')).toBeInTheDocument();
    const desktop = screen.getByRole('navigation', { name: 'Main' });
    const mobile = screen.getByRole('navigation', { name: 'Main (mobile)' });
    for (const nav of [desktop, mobile]) {
      expect(within(nav).getByRole('link', { name: 'Calendar' })).toBeInTheDocument();
      expect(within(nav).getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    }
    expect(screen.getByRole('main')).toHaveTextContent('Calendar coming in phase 3');
  });

  it('shows a non-blocking notice while the API is not ready', async () => {
    renderApp();
    expect(await screen.findByRole('status')).toHaveTextContent('API not ready');
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('has a skip link to the main landmark', () => {
    renderApp();
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
  });

  it('changes the theme from settings', async () => {
    renderApp('/settings');
    await userEvent.selectOptions(screen.getByLabelText('Theme'), 'dark');
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(window.localStorage.getItem('hoje.theme')).toBe('dark');
  });
});
