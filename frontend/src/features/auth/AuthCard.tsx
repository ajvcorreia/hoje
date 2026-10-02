import type { ReactNode } from 'react';

/** Centred card used by every public auth screen. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-[360px]">
        <p className="mb-6 text-center text-2xl font-semibold tracking-tight">Hoje</p>
        <div className="rounded-lg border border-border bg-surface p-5">
          <h1 className="mb-4 text-lg font-semibold">{title}</h1>
          {children}
        </div>
      </div>
    </div>
  );
}
