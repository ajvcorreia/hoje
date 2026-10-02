import { useId, type ReactNode } from 'react';

export function SettingsSection({
  title,
  id,
  children,
}: {
  title: string;
  /** Anchor for links such as `/settings#vacation`. */
  id?: string;
  children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className="scroll-mt-16 rounded-lg border border-border bg-surface p-4"
    >
      <h2 id={headingId} className="text-base font-semibold">
        {title}
      </h2>
      <div className="mt-3 space-y-4">{children}</div>
    </section>
  );
}
