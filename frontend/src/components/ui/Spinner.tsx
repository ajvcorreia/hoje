/** Minimal centred full-page spinner. */
export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" className="flex min-h-dvh items-center justify-center">
      <span
        aria-hidden="true"
        className="size-6 animate-spin rounded-full border-2 border-border border-t-accent"
      />
      <span className="sr-only">{label}</span>
    </div>
  );
}
