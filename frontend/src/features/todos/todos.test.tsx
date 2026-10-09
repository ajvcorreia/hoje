import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createQueryClient } from '../../app/queryClient';
import { ToastProvider } from '../../components/ui/Toast';
import { todayIso } from '../../lib/dates';
import { ME, authState, mockApi, renderApp } from '../../test/utils';
import { keysForChange } from '../realtime/realtimeKeys';
import { TodoSection } from './TodoSection';

const base = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/me': ME,
  'GET /api/v1/settings/email': { configured: false, from_address: null },
};

function todo(overrides: Record<string, unknown> = {}) {
  const today = todayIso();
  return {
    id: crypto.randomUUID(),
    title: 'Pay rent',
    day: today,
    due_date: null,
    done: false,
    completed_on: null,
    shown_on: today,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    ...overrides,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('due to-dos pop-up', () => {
  it('opens on page load with the to-dos due today or overdue and lets you check one off', async () => {
    const due = todo({ title: 'Call the bank', due_date: todayIso() });
    const api = mockApi({
      ...base,
      'GET /api/v1/todos/due': { todos: [due] },
      [`PATCH /api/v1/todos/${String(due.id)}`]: { ...due, done: true },
    });
    renderApp('/settings');
    const dialog = await screen.findByRole('dialog', { name: 'To-dos due' });
    expect(dialog).toHaveTextContent('Call the bank');
    expect(dialog).toHaveTextContent('Due today');

    await userEvent.click(screen.getByRole('checkbox', { name: /Call the bank/ }));
    const path = `/api/v1/todos/${String(due.id)}`;
    await waitFor(() => expect(api.callsTo('PATCH', path)).toHaveLength(1));
    expect(api.callsTo('PATCH', path)[0]?.body).toEqual({ done: true });

    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog', { name: 'To-dos due' })).not.toBeInTheDocument();
  });

  it('marks overdue to-dos', async () => {
    mockApi({
      ...base,
      'GET /api/v1/todos/due': { todos: [todo({ title: 'Old', due_date: '2020-01-02' })] },
    });
    renderApp('/settings');
    expect(await screen.findByText(/Overdue · 2 Jan 2020/)).toBeInTheDocument();
  });

  it('stays closed when nothing is due', async () => {
    mockApi({ ...base, 'GET /api/v1/todos/due': { todos: [] } });
    renderApp('/settings');
    await screen.findByRole('heading', { name: 'Email' });
    expect(screen.queryByRole('dialog', { name: 'To-dos due' })).not.toBeInTheDocument();
  });
});

describe('TodoSection', () => {
  function renderSection(date: string) {
    const queryClient = createQueryClient();
    queryClient.setDefaultOptions({ queries: { retry: false } });
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <TodoSection date={date} />
        </ToastProvider>
      </QueryClientProvider>,
    );
  }

  it('lists carried-over and finished to-dos and adds a new one with a due date', async () => {
    const date = todayIso();
    const carried = todo({ title: 'Carried', day: '2020-01-02', shown_on: date });
    const finished = todo({ title: 'Finished', done: true, completed_on: date });
    const created = todo({ title: 'Book flight', due_date: '2099-03-04' });
    const api = mockApi({
      'GET /api/v1/todos': { todos: [carried, finished] },
      'POST /api/v1/todos': created,
    });
    renderSection(date);
    expect(await screen.findByText('Carried')).toBeInTheDocument();
    expect(screen.getByText(/from 2 Jan 2020/)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Finished/ })).toBeChecked();

    await userEvent.type(screen.getByLabelText('Add a to-do'), 'Book flight');
    await userEvent.type(screen.getByLabelText('Due date (optional)'), '2099-03-04');
    await userEvent.type(screen.getByLabelText('Add a to-do'), '{Enter}');
    await waitFor(() => expect(api.callsTo('POST', '/api/v1/todos')).toHaveLength(1));
    expect(api.callsTo('POST', '/api/v1/todos')[0]?.body).toEqual({
      title: 'Book flight',
      day: date,
      due_date: '2099-03-04',
    });
    expect(screen.getByLabelText('Add a to-do')).toHaveValue('');
  });

  it('deletes a to-do', async () => {
    const item = todo({ title: 'Remove me' });
    const path = `/api/v1/todos/${String(item.id)}`;
    const api = mockApi({
      'GET /api/v1/todos': { todos: [item] },
      [`DELETE ${path}`]: null,
    });
    renderSection(todayIso());
    await userEvent.click(await screen.findByRole('button', { name: 'Delete to-do Remove me' }));
    await waitFor(() => expect(api.callsTo('DELETE', path)).toHaveLength(1));
  });
});

describe('live sync', () => {
  it('refreshes every to-do list on a todo change', () => {
    const keys = keysForChange({
      entity: 'todo',
      op: 'update',
      id: 'x',
      version: 0,
      client_id: null,
    });
    expect(keys).toEqual([['todos']]);
  });
});
