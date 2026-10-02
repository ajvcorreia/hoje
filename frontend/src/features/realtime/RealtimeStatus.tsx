import { useEffect, useState } from 'react';
import { useRealtimeState } from './store';

const UPDATED_VISIBLE_MS = 3000;

/** Header pills: "Updated" after another device changed something, "Offline" when the stream is down. */
export function RealtimeStatus() {
  const { offline, remoteTick } = useRealtimeState();
  // Ticks already faded / hidden; the pill shows for the newest tick until its timers fire.
  const [fadingTick, setFadingTick] = useState(0);
  const [hiddenTick, setHiddenTick] = useState(0);
  const shown = remoteTick > hiddenTick;
  const fading = fadingTick === remoteTick;

  useEffect(() => {
    if (remoteTick === 0) return;
    const fade = setTimeout(() => setFadingTick(remoteTick), UPDATED_VISIBLE_MS - 500);
    const hide = setTimeout(() => setHiddenTick(remoteTick), UPDATED_VISIBLE_MS);
    return () => {
      clearTimeout(fade);
      clearTimeout(hide);
    };
  }, [remoteTick]);

  return (
    <>
      {offline ? (
        <span
          role="status"
          aria-live="polite"
          className="rounded-full border border-border bg-surface-muted px-2.5 py-0.5 text-xs text-text-muted"
        >
          Offline — reconnecting…
        </span>
      ) : null}
      {shown ? (
        <span
          role="status"
          aria-live="polite"
          className={`inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-muted px-2.5 py-0.5 text-xs text-text-muted transition-opacity duration-500 ${
            fading ? 'opacity-0' : 'opacity-100'
          }`}
        >
          <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
          Updated
        </span>
      ) : null}
    </>
  );
}
