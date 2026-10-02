/**
 * Returns `next` only when it is a same-origin relative path (`/x`), never a
 * protocol-relative (`//host`), backslash-tricked or absolute URL. Otherwise `fallback`.
 */
export function safeNext(next: string | null | undefined, fallback = '/'): string {
  if (!next) return fallback;
  if (!next.startsWith('/') || next.startsWith('//')) return fallback;
  // Browsers treat a backslash like "/" in URLs, and control characters can hide a scheme.
  if (next.includes('\\')) return fallback;
  for (const ch of next) {
    const code = ch.charCodeAt(0);
    if (code < 0x20 || code === 0x7f) return fallback;
  }
  return next;
}
