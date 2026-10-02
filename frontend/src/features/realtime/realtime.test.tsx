import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiClient } from '../../api/client';
import { getClientId } from '../../api/clientId';
import { ToastProvider } from '../../components/ui/Toast';
import { mockApi } from '../../test/utils';
import { EventEditor } from '../events/EventEditor';
import { setEventSourceFactory, type EventSourceLike } from './connection';
import { RealtimeStatus } from './RealtimeStatus';
import type { ChangeMessage } from './realtimeKeys';
import { emitChange } from './store';
import { useRealtime } from './useRealtime';

class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];
  onopen: ((e: Event) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  closed = false;
  private listeners = new Map<string, ((e: MessageEvent<string>) => void)[]>();
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (e: MessageEvent<string>) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.onopen?.(new Event('open'));
  }
  fail() {
    this.onerror?.(new Event('error'));
  }
  send(type: string, data: unknown = {}) {
    const event = { data: JSON.stringify(data) } as MessageEvent<string>;
    this.listeners.get(type)?.forEach((l) => l(event));
  }
}

const latest = () => FakeEventSource.instances[FakeEventSource.instances.length - 1]!;
const EVENT_ID = 'bbbbbbbb-0000-0000-0000-000000000001';

function change(over: Partial<ChangeMessage> = {}): ChangeMessage {
  return {
    entity: 'event',
    op: 'update',
    id: EVENT_ID,
    version: 2,
    client_id: 'other-tab-id',
    ...over,
  };
}

function Harness() {
  useRealtime();
  return <RealtimeStatus />;
}

function mount() {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, 'invalidateQueries');
  const view = render(
    <QueryClientProvider client={qc}>
      <Harness />
    </QueryClientProvider>,
  );
  return { qc, spy, view };
}

const keyCalls = (spy: ReturnType<typeof mount>['spy'], key: unknown[]) =>
  spy.mock.calls.filter(([f]) => JSON.stringify(f?.queryKey) === JSON.stringify(key)).length;

let visibility: 'visible' | 'hidden' = 'visible';
function setVisibility(value: 'visible' | 'hidden') {
  visibility = value;
  document.dispatchEvent(new Event('visibilitychange'));
}

const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

beforeEach(() => {
  FakeEventSource.instances = [];
  visibility = 'visible';
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility });
  setEventSourceFactory((url) => new FakeEventSource(url));
  vi.spyOn(Math, 'random').mockReturnValue(1); // full jitter pinned to its upper bound
});

afterEach(() => {
  setEventSourceFactory();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('X-Hoje-Client header', () => {
  it('is sent on writes only', async () => {
    const seen: { method: string; client: string | null }[] = [];
    const fetchStub = vi.fn(async (input: RequestInfo | URL) => {
      const request = input as Request;
      seen.push({ method: request.method, client: request.headers.get('X-Hoje-Client') });
      return Response.json({});
    });
    const client = createApiClient({ baseUrl: 'http://localhost', fetch: fetchStub });
    await client.GET('/api/v1/categories');
    await client.POST('/api/v1/auth/logout');
    await client.DELETE('/api/v1/events/{event_id}', { params: { path: { event_id: EVENT_ID } } });
    expect(seen.map((s) => s.method)).toEqual(['GET', 'POST', 'DELETE']);
    expect(seen[0]?.client).toBeNull();
    expect(seen[1]?.client).toBe(getClientId());
    expect(seen[2]?.client).toBe(getClientId());
    expect(getClientId()).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  });
});

describe('live sync stream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it('a change from another client invalidates occurrences and shows Updated', () => {
    const { spy } = mount();
    act(() => latest().open());
    act(() => latest().send('change', change()));
    advance(150);
    expect(keyCalls(spy, ['occurrences'])).toBe(1);
    expect(keyCalls(spy, ['event', EVENT_ID])).toBe(1);
    expect(screen.getByText('Updated')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
    advance(3100);
    expect(screen.queryByText('Updated')).not.toBeInTheDocument();
  });

  it('own changes refresh silently', () => {
    const { spy } = mount();
    act(() => latest().open());
    act(() => latest().send('change', change({ client_id: getClientId() })));
    advance(150);
    expect(keyCalls(spy, ['occurrences'])).toBe(1);
    expect(screen.queryByText('Updated')).not.toBeInTheDocument();
  });

  it('coalesces a burst of 50 event changes into one invalidation per key', () => {
    const { spy } = mount();
    act(() => latest().open());
    act(() => {
      for (let i = 0; i < 50; i += 1) {
        latest().send(
          'change',
          change({ id: `cccccccc-0000-0000-0000-${String(i).padStart(12, '0')}` }),
        );
      }
    });
    expect(spy).not.toHaveBeenCalled();
    advance(150);
    expect(keyCalls(spy, ['occurrences'])).toBe(1);
    expect(keyCalls(spy, ['events', 'search'])).toBe(1);
  });

  it('maps category changes to categories and occurrences', () => {
    const { spy } = mount();
    act(() => latest().open());
    act(() => latest().send('change', change({ entity: 'category' })));
    advance(150);
    expect(keyCalls(spy, ['categories'])).toBe(1);
    expect(keyCalls(spy, ['occurrences'])).toBe(1);
  });

  it('resync invalidates everything', () => {
    const { spy } = mount();
    act(() => latest().open());
    act(() => latest().send('resync'));
    expect(spy).toHaveBeenCalledWith();
  });

  it('reconnects with exponential backoff and refetches everything afterwards', () => {
    const { spy } = mount();
    expect(FakeEventSource.instances).toHaveLength(1);
    act(() => latest().open());
    expect(spy).not.toHaveBeenCalled(); // first open: nothing was missed

    const first = latest();
    act(() => first.fail());
    expect(first.closed).toBe(true);
    advance(999);
    expect(FakeEventSource.instances).toHaveLength(1);
    advance(1);
    expect(FakeEventSource.instances).toHaveLength(2);

    act(() => latest().fail()); // second failure: 2 s
    advance(1999);
    expect(FakeEventSource.instances).toHaveLength(2);
    advance(1);
    expect(FakeEventSource.instances).toHaveLength(3);

    spy.mockClear();
    act(() => latest().open());
    expect(spy).toHaveBeenCalledWith();
  });

  it('shows the offline pill after 10 s without a connection and hides it on reconnect', () => {
    mount();
    act(() => latest().open());
    act(() => latest().fail());
    advance(9000);
    expect(screen.queryByText(/Offline/)).not.toBeInTheDocument();
    advance(1500);
    expect(screen.getByText('Offline — reconnecting…')).toBeInTheDocument();
    act(() => latest().open());
    expect(screen.queryByText(/Offline/)).not.toBeInTheDocument();
  });

  it('closes after 5 minutes hidden and reopens with a full refetch when visible', () => {
    const { spy } = mount();
    act(() => latest().open());
    const stream = latest();
    act(() => setVisibility('hidden'));
    advance(4 * 60_000);
    expect(stream.closed).toBe(false);
    advance(60_000);
    expect(stream.closed).toBe(true);
    act(() => setVisibility('visible'));
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => latest().open());
    expect(spy).toHaveBeenCalledWith();
  });

  it('stays connected when hidden only briefly', () => {
    mount();
    act(() => latest().open());
    act(() => setVisibility('hidden'));
    advance(60_000);
    act(() => setVisibility('visible'));
    advance(10 * 60_000);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(latest().closed).toBe(false);
  });

  it('closes the stream on unmount', () => {
    const { view } = mount();
    act(() => latest().open());
    const stream = latest();
    view.unmount();
    expect(stream.closed).toBe(true);
  });
});

describe('edit conflict notice', () => {
  const CATEGORY = 'aaaaaaaa-0000-0000-0000-000000000001';
  const event = (over: Record<string, unknown> = {}) => ({
    id: EVENT_ID,
    category_id: CATEGORY,
    title: 'Dentist',
    notes: null,
    start_date: '2026-10-15',
    end_date: '2026-10-15',
    all_day: true,
    start_time: null,
    end_time: null,
    timezone: 'UTC',
    repeat: 'none',
    repeat_until: null,
    counts_as_leave: false,
    label_vertical: false,
    reminders: [],
    version: 1,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    ...over,
  });

  function openEditor() {
    const onClose = vi.fn();
    let served = 0;
    const api = mockApi({
      'GET /api/v1/categories': [
        {
          id: CATEGORY,
          name: 'Work',
          colour: 'teal',
          icon: null,
          sort_order: 0,
          is_leave: false,
          hidden: false,
          version: 1,
        },
      ],
      [`GET /api/v1/events/${EVENT_ID}`]: () => {
        served += 1;
        return served === 1 ? event() : event({ title: 'Dentist (moved)', version: 2 });
      },
    });
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <ToastProvider>
          <EventEditor mode="edit" eventId={EVENT_ID} onClose={onClose} />
        </ToastProvider>
      </QueryClientProvider>,
    );
    return { api, onClose };
  }

  it('offers Load latest / Keep editing when another device updates the event', async () => {
    const user = userEvent.setup();
    const { api } = openEditor();
    const title = await screen.findByLabelText('Title');
    await user.type(title, ' x');

    act(() => emitChange(change({ client_id: getClientId() }))); // own: ignored
    act(() => emitChange(change({ version: 1 }))); // not newer: ignored
    expect(screen.queryByText(/another device/)).not.toBeInTheDocument();

    act(() => emitChange(change()));
    expect(screen.getByText('This event was changed on another device.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Keep editing' }));
    expect(screen.queryByText(/another device/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toHaveValue('Dentist x');

    act(() => emitChange(change({ version: 3 })));
    await user.click(screen.getByRole('button', { name: 'Load latest' }));
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('Dentist (moved)'));
    expect(api.callsTo('GET', `/api/v1/events/${EVENT_ID}`).length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/another device/)).not.toBeInTheDocument();
  });

  it('tells the user when the event was deleted on another device', async () => {
    const user = userEvent.setup();
    const { onClose } = openEditor();
    await screen.findByLabelText('Title');
    act(() => emitChange(change({ op: 'delete', version: 1 })));
    expect(screen.getByText('This event was deleted on another device.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load latest' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalled();
  });
});
