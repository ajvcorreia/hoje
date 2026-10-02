/** Shared Tailwind class strings for flat, hairline-bordered controls. */
export const inputClass =
  'block min-h-11 w-full rounded-md border border-border bg-surface px-3 text-base text-text placeholder:text-text-muted md:min-h-9 md:text-sm';

const btnBase =
  'inline-flex min-h-11 items-center justify-center rounded-md px-4 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60 md:min-h-9';

export const btnPrimary = `${btnBase} bg-accent text-accent-contrast hover:opacity-90`;
export const btnSecondary = `${btnBase} border border-border bg-surface text-text hover:bg-surface-muted`;
export const btnDanger = `${btnBase} border border-danger bg-surface text-danger hover:bg-surface-muted`;
export const linkClass = 'text-accent underline-offset-2 hover:underline';
