import type { QueryClient } from '@tanstack/react-query';
import { getClientId } from '../../api/clientId';
import { AUTH_STATE_KEY } from '../../app/useAuthState';
import { keysForChange, type ChangeMessage } from './realtimeKeys';
import { emitChange, getRealtimeState, setRealtimeState } from './store';

export const STREAM_URL = '/api/v1/realtime/stream';

/** The slice of EventSource this module uses (lets tests supply a fake). */
export interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void;
  close(): void;
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
}

type Factory = (url: string) => EventSourceLike | null;

const defaultFactory: Factory = (url) =>
  typeof EventSource === 'undefined' ? null : new EventSource(url, { withCredentials: false });

let factory: Factory = defaultFactory;

/** Test seam: replace how the stream is opened. Pass nothing to restore the default. */
export function setEventSourceFactory(next?: Factory) {
  factory = next ?? defaultFactory;
}

export interface RealtimeOptions {
  queryClient: QueryClient;
  /** Returns [0, 1); tests pin it to get deterministic backoff. */
  random?: () => number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  stableAfterMs?: number;
  hiddenPauseMs?: number;
  offlineAfterMs?: number;
  debounceMs?: number;
}

function parseChange(data: string): ChangeMessage | null {
  try {
    const value = JSON.parse(data) as Partial<ChangeMessage> | null;
    if (value && typeof value.entity === 'string' && typeof value.id === 'string') {
      return {
        entity: value.entity,
        op: value.op ?? 'update',
        id: value.id,
        version: typeof value.version === 'number' ? value.version : 0,
        client_id: value.client_id ?? null,
      };
    }
  } catch {
    // Ignore malformed frames.
  }
  return null;
}

/**
 * Owns the SSE stream: reconnects with exponential backoff and full jitter, pauses while the
 * tab is hidden for a long time, and turns change messages into (coalesced) query invalidations.
 */
export function createRealtimeController(options: RealtimeOptions) {
  const qc = options.queryClient;
  const random = options.random ?? Math.random;
  const baseDelay = options.baseDelayMs ?? 1000;
  const maxDelay = options.maxDelayMs ?? 30_000;
  const stableAfter = options.stableAfterMs ?? 60_000;
  const hiddenPause = options.hiddenPauseMs ?? 5 * 60_000;
  const offlineAfter = options.offlineAfterMs ?? 10_000;
  const debounce = options.debounceMs ?? 150;

  let source: EventSourceLike | null = null;
  let running = false;
  let paused = false;
  let attempt = 0;
  /** True once something may have been missed: the next open must refetch everything. */
  let needsFullRefetch = false;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let stableTimer: ReturnType<typeof setTimeout> | undefined;
  let offlineTimer: ReturnType<typeof setTimeout> | undefined;
  let hiddenTimer: ReturnType<typeof setTimeout> | undefined;
  let flushTimer: ReturnType<typeof setTimeout> | undefined;
  const pending = new Map<string, readonly unknown[]>();

  const invalidateAll = () => {
    pending.clear();
    clearTimeout(flushTimer);
    flushTimer = undefined;
    void qc.invalidateQueries();
  };

  const flush = () => {
    flushTimer = undefined;
    const keys = [...pending.values()];
    pending.clear();
    for (const queryKey of keys) void qc.invalidateQueries({ queryKey });
  };

  const onChange = (data: string) => {
    const change = parseChange(data);
    if (!change) return;
    for (const key of keysForChange(change)) pending.set(JSON.stringify(key), key);
    if (pending.size > 0 && flushTimer === undefined) flushTimer = setTimeout(flush, debounce);
    if (change.client_id !== getClientId()) {
      setRealtimeState({ remoteTick: getRealtimeState().remoteTick + 1 });
    }
    emitChange(change);
  };

  const markConnected = () => {
    clearTimeout(offlineTimer);
    offlineTimer = undefined;
    if (getRealtimeState().offline) setRealtimeState({ offline: false });
  };

  const markDisconnected = () => {
    if (offlineTimer === undefined) {
      offlineTimer = setTimeout(() => setRealtimeState({ offline: true }), offlineAfter);
    }
  };

  const closeSource = () => {
    const current = source;
    source = null;
    if (current) {
      current.onopen = null;
      current.onerror = null;
      current.close();
    }
  };

  const open = () => {
    if (!running || paused || source) return;
    const es = factory(STREAM_URL);
    if (!es) return;
    source = es;
    es.onopen = () => {
      if (source !== es) return;
      markConnected();
      clearTimeout(stableTimer);
      stableTimer = setTimeout(() => {
        attempt = 0;
      }, stableAfter);
      if (needsFullRefetch) {
        needsFullRefetch = false;
        invalidateAll();
      }
    };
    es.addEventListener('change', (e) => {
      if (source === es) onChange(e.data);
    });
    es.addEventListener('resync', () => {
      if (source === es) invalidateAll();
    });
    es.onerror = () => {
      if (source !== es) return;
      closeSource();
      clearTimeout(stableTimer);
      needsFullRefetch = true;
      markDisconnected();
      // Repeated failures may mean the session is gone: refresh the auth state so the route
      // guard can send the user to login instead of retrying forever.
      if (attempt >= 1) void qc.invalidateQueries({ queryKey: AUTH_STATE_KEY });
      const cap = Math.min(maxDelay, baseDelay * 2 ** attempt);
      attempt += 1;
      clearTimeout(retryTimer);
      retryTimer = setTimeout(open, random() * cap);
    };
  };

  const pause = () => {
    paused = true;
    needsFullRefetch = true;
    clearTimeout(retryTimer);
    clearTimeout(stableTimer);
    clearTimeout(offlineTimer);
    offlineTimer = undefined;
    closeSource();
  };

  const onVisibility = () => {
    if (!running) return;
    if (document.visibilityState === 'hidden') {
      if (hiddenTimer === undefined) hiddenTimer = setTimeout(pause, hiddenPause);
      return;
    }
    clearTimeout(hiddenTimer);
    hiddenTimer = undefined;
    if (paused) {
      paused = false;
      attempt = 0;
      open();
    }
  };

  return {
    start() {
      if (running) return;
      running = true;
      document.addEventListener('visibilitychange', onVisibility);
      open();
      onVisibility();
    },
    stop() {
      running = false;
      document.removeEventListener('visibilitychange', onVisibility);
      [retryTimer, stableTimer, offlineTimer, hiddenTimer, flushTimer].forEach(clearTimeout);
      retryTimer = stableTimer = offlineTimer = hiddenTimer = flushTimer = undefined;
      pending.clear();
      closeSource();
      setRealtimeState({ offline: false, remoteTick: 0 });
    },
  };
}
