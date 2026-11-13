import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

  it('edits the title and due date, sending only what changed', async () => {
    let item = todo({ title: 'Pay rent', due_date: '2099-01-02' });
    const path = `/api/v1/todos/${String(item.id)}`;
    const api = mockApi({
      'GET /api/v1/todos': () => ({ todos: [item] }),
      [`PATCH ${path}`]: (call) => (item = { ...item, ...(call.body as object) }),
    });
    renderSection(todayIso());
    await userEvent.click(await screen.findByRole('button', { name: 'Edit to-do Pay rent' }));
    const title = screen.getByLabelText('To-do');
    expect(title).toHaveFocus();
    expect(screen.getByLabelText('Due date')).toHaveValue('2099-01-02');
    await userEvent.clear(title);
    await userEvent.type(title, 'Pay the rent');
    await userEvent.clear(screen.getByLabelText('Due date'));
    await userEvent.type(screen.getByLabelText('Due date'), '2099-05-06');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.callsTo('PATCH', path)).toHaveLength(1));
    expect(api.callsTo('PATCH', path)[0]?.body).toEqual({
      title: 'Pay the rent',
      due_date: '2099-05-06',
    });
    expect(await screen.findByText('Pay the rent')).toBeInTheDocument();
    expect(screen.queryByLabelText('To-do')).not.toBeInTheDocument();
  });

  it('clears the due date', async () => {
    const item = todo({ title: 'Call mum', due_date: '2099-01-02' });
    const path = `/api/v1/todos/${String(item.id)}`;
    const api = mockApi({
      'GET /api/v1/todos': { todos: [item] },
      [`PATCH ${path}`]: { ...item, due_date: null },
    });
    renderSection(todayIso());
    await userEvent.click(await screen.findByRole('button', { name: 'Edit to-do Call mum' }));
    await userEvent.clear(screen.getByLabelText('Due date'));
    await userEvent.type(screen.getByLabelText('To-do'), '{Enter}');
    await waitFor(() => expect(api.callsTo('PATCH', path)).toHaveLength(1));
    expect(api.callsTo('PATCH', path)[0]?.body).toEqual({ due_date: null });
  });

  it('sends nothing when cancelled, unchanged, or emptied', async () => {
    const item = todo({ title: 'Keep me' });
    const path = `/api/v1/todos/${String(item.id)}`;
    const api = mockApi({ 'GET /api/v1/todos': { todos: [item] } });
    renderSection(todayIso());

    await userEvent.click(await screen.findByRole('button', { name: 'Edit to-do Keep me' }));
    await userEvent.type(screen.getByLabelText('To-do'), ' later{Escape}');
    expect(screen.queryByLabelText('To-do')).not.toBeInTheDocument();
    expect(screen.getByText('Keep me')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Edit to-do Keep me' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.queryByLabelText('To-do')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Edit to-do Keep me' }));
    await userEvent.clear(screen.getByLabelText('To-do'));
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByLabelText('To-do')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(api.callsTo('PATCH', path)).toHaveLength(0);
  });
});

describe('to-do column', () => {
  const today = todayIso();
  const later = '2099-03-04';
  const routes = (column: string, extra: Record<string, unknown> = {}) => ({
    ...base,
    'GET /api/v1/auth/state': authState({ user: { ...ME, todo_column: column } }),
    'GET /api/v1/todos/due': { todos: [] },
    'GET /api/v1/todos/open': {
      todos: [
        todo({ title: 'Someday' }),
        todo({ title: 'Later thing', due_date: later }),
        todo({ title: 'Now thing', due_date: today }),
        todo({ title: 'Late thing', due_date: '2020-01-02' }),
      ],
    },
    'GET /api/v1/events/occurrences': { occurrences: [] },
    'GET /api/v1/categories': { categories: [] },
    'GET /api/v1/holidays/overlay': { days: [] },
    ...extra,
  });

  it('is hidden while the setting is off', async () => {
    mockApi(routes('off'));
    renderApp('/');
    await screen.findByRole('heading', { name: 'Calendar' });
    expect(screen.queryByRole('complementary', { name: 'To-do list' })).not.toBeInTheDocument();
  });

  it('lists the open to-dos in their three sections', async () => {
    mockApi(routes('right'));
    renderApp('/');
    const column = await screen.findByRole('complementary', { name: 'To-do list' });
    const section = (name: string) => within(column).getByRole('region', { name });
    await waitFor(() => expect(section('No due date')).toHaveTextContent('Someday'));
    expect(section('Due today')).toHaveTextContent('Now thing');
    expect(section('Due today')).toHaveTextContent(/Late thing.*Overdue/);
    // Overdue first, then today.
    expect(section('Due today').textContent?.indexOf('Late thing')).toBeLessThan(
      section('Due today').textContent?.indexOf('Now thing') ?? 0,
    );
    expect(section('Due later')).toHaveTextContent('Later thing');
    expect(section('No due date')).not.toHaveTextContent('Later thing');
  });

  it('adds a to-do with an optional due date', async () => {
    const api = mockApi(
      routes('left', { 'POST /api/v1/todos': todo({ title: 'New one', due_date: later }) }),
    );
    renderApp('/');
    const column = await screen.findByRole('complementary', { name: 'To-do list' });
    await userEvent.type(within(column).getByLabelText('Add a to-do'), 'New one');
    fireEvent.change(within(column).getByLabelText('Due date (optional)'), {
      target: { value: later },
    });
    await userEvent.click(within(column).getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(api.callsTo('POST', '/api/v1/todos')).toHaveLength(1));
    expect(api.callsTo('POST', '/api/v1/todos')[0]?.body).toEqual({
      title: 'New one',
      due_date: later,
    });
  });

  it('opens the done to-dos grouped by the day they were done, newest first', async () => {
    const done = (title: string, on: string, at: string) =>
      todo({ title, done: true, completed_on: on, shown_on: on, done_at: at });
    const api = mockApi(
      routes('right', {
        'GET /api/v1/todos/done': {
          todos: [
            done('Filed taxes', '2026-11-12', '2026-11-12T18:00:00Z'),
            done('Bought milk', '2026-11-12', '2026-11-12T09:00:00Z'),
            done('Called mum', '2026-11-03', '2026-11-03T10:00:00Z'),
          ],
        },
      }),
    );
    renderApp('/');
    const column = await screen.findByRole('complementary', { name: 'To-do list' });
    expect(api.callsTo('GET', '/api/v1/todos/done')).toHaveLength(0);
    await userEvent.click(within(column).getByRole('button', { name: 'Done' }));
    const dialog = await screen.findByRole('dialog', { name: 'Done to-dos' });
    const groups = await within(dialog).findAllByRole('region');
    expect(groups.map((g) => g.getAttribute('aria-label'))).toEqual([
      'Done on 2026-11-12',
      'Done on 2026-11-03',
    ]);
    expect(groups[0]?.textContent?.indexOf('Filed taxes')).toBeLessThan(
      groups[0]?.textContent?.indexOf('Bought milk') ?? 0,
    );
    expect(within(dialog).getByRole('checkbox', { name: /Called mum/ })).toBeChecked();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog', { name: 'Done to-dos' })).not.toBeInTheDocument();
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
