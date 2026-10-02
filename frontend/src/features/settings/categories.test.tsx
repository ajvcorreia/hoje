import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ME, authState, mockApi, renderApp } from '../../test/utils';

const WORK = 'aaaaaaaa-0000-0000-0000-000000000001';
const HOME = 'aaaaaaaa-0000-0000-0000-000000000002';

const CATEGORIES = [
  { id: WORK, name: 'Work', colour: 'teal', icon: null, sort_order: 0, is_leave: false, hidden: false, version: 1 },
  { id: HOME, name: 'Home', colour: 'pink', icon: null, sort_order: 1, is_leave: true, hidden: false, version: 2 },
];

const base = {
  'GET /api/v1/auth/state': authState(),
  'GET /api/v1/me': ME,
  'GET /api/v1/settings/email': { configured: true, from_address: 'hoje@example.com' },
  'GET /api/v1/categories': CATEGORIES,
};

describe('settings › categories', () => {
  it('lists categories and renames one inline', async () => {
    const api = mockApi({
      ...base,
      [`PATCH /api/v1/categories/${WORK}`]: (call) => ({ ...CATEGORIES[0], ...(call.body as object) }),
    });
    renderApp('/settings');
    const input = await screen.findByLabelText('Name of Work');
    expect(screen.getByLabelText('Name of Home')).toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, 'Office{Enter}');
    await waitFor(() => expect(api.callsTo('PATCH', `/api/v1/categories/${WORK}`)).toHaveLength(1));
    expect(api.callsTo('PATCH', `/api/v1/categories/${WORK}`)[0]?.body).toEqual({
      name: 'Office',
      version: 1,
    });
  });

  it('recolours with a labelled palette and toggles vacation', async () => {
    const api = mockApi({
      ...base,
      [`PATCH /api/v1/categories/${WORK}`]: (call) => ({ ...CATEGORIES[0], ...(call.body as object) }),
    });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: /Colour of Work/ }));
    const picker = screen.getByRole('radiogroup', { name: 'Colour for Work' });
    expect(within(picker).getAllByRole('radio')).toHaveLength(12);
    expect(within(picker).getByRole('radio', { name: 'Teal' })).toHaveAttribute('aria-checked', 'true');
    await userEvent.click(within(picker).getByRole('radio', { name: 'Violet' }));
    await waitFor(() => expect(api.callsTo('PATCH', `/api/v1/categories/${WORK}`)).toHaveLength(1));
    expect(api.callsTo('PATCH', `/api/v1/categories/${WORK}`)[0]?.body).toEqual({
      colour: 'violet',
      version: 1,
    });

    await userEvent.click(screen.getByRole('checkbox', { name: /Counts as vacation for Work/ }));
    await waitFor(() => expect(api.callsTo('PATCH', `/api/v1/categories/${WORK}`)).toHaveLength(2));
    expect(api.callsTo('PATCH', `/api/v1/categories/${WORK}`)[1]?.body).toMatchObject({
      is_leave: true,
    });
  });

  it('reorders with the up/down buttons', async () => {
    const api = mockApi({
      ...base,
      'PUT /api/v1/categories/order': [CATEGORIES[1], CATEGORIES[0]],
    });
    renderApp('/settings');
    expect(await screen.findByRole('button', { name: 'Move Work up' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Move Work down' }));
    await waitFor(() => expect(api.callsTo('PUT', '/api/v1/categories/order')).toHaveLength(1));
    expect(api.callsTo('PUT', '/api/v1/categories/order')[0]?.body).toEqual({ ids: [HOME, WORK] });
  });

  it('adds a category', async () => {
    const api = mockApi({
      ...base,
      'POST /api/v1/categories': (call) => ({
        ...(call.body as object),
        id: 'new',
        icon: null,
        sort_order: 2,
        is_leave: false,
        hidden: false,
        version: 1,
      }),
    });
    renderApp('/settings');
    await userEvent.type(await screen.findByLabelText('New category name'), 'Travel');
    await userEvent.click(screen.getByRole('radio', { name: 'Blue' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(api.callsTo('POST', '/api/v1/categories')).toHaveLength(1));
    expect(api.callsTo('POST', '/api/v1/categories')[0]?.body).toEqual({
      name: 'Travel',
      colour: 'blue',
    });
  });

  it('asks where to move events before deleting', async () => {
    const api = mockApi({ ...base, [`DELETE /api/v1/categories/${WORK}`]: null });
    renderApp('/settings');
    await userEvent.click(await screen.findByRole('button', { name: 'Delete Work' }));
    const dialog = await screen.findByRole('dialog', { name: 'Delete Work?' });
    expect(within(dialog).getByLabelText('Move its events to')).toHaveValue(HOME);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete category' }));
    await waitFor(() => expect(api.callsTo('DELETE', `/api/v1/categories/${WORK}`)).toHaveLength(1));
    expect(api.callsTo('DELETE', `/api/v1/categories/${WORK}`)[0]?.search).toBe(
      `?reassign_to=${HOME}`,
    );
  });
});
