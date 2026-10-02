import { useSyncExternalStore } from 'react';
import type { ChangeMessage } from './realtimeKeys';

export interface RealtimeState {
  /** Disconnected for longer than the grace period. */
  offline: boolean;
  /** Increments whenever another client changed something. */
  remoteTick: number;
}

let state: RealtimeState = { offline: false, remoteTick: 0 };
const stateListeners = new Set<() => void>();
const changeListeners = new Set<(change: ChangeMessage) => void>();

export function setRealtimeState(patch: Partial<RealtimeState>) {
  state = { ...state, ...patch };
  stateListeners.forEach((l) => l());
}

export function getRealtimeState() {
  return state;
}

export function useRealtimeState(): RealtimeState {
  return useSyncExternalStore(
    (l) => {
      stateListeners.add(l);
      return () => {
        stateListeners.delete(l);
      };
    },
    () => state,
  );
}

/** Raw (un-debounced) change messages from this and other clients. */
export function subscribeChanges(listener: (change: ChangeMessage) => void) {
  changeListeners.add(listener);
  return () => {
    changeListeners.delete(listener);
  };
}

export function emitChange(change: ChangeMessage) {
  changeListeners.forEach((l) => l(change));
}
