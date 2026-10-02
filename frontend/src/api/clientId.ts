const STORAGE_KEY = 'hoje.clientId';
const VALID = /^[A-Za-z0-9_-]{8,64}$/;

let cached: string | null = null;

function generate(): string {
  const bytes = new Uint8Array(16);
  // getRandomValues works in insecure contexts too (the LAN test stack runs over HTTP).
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
  else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Random id of this browser tab, sent as `X-Hoje-Client` so the server can echo it in change events. */
export function getClientId(): string {
  if (cached) return cached;
  let id: string | null = null;
  try {
    const stored = globalThis.sessionStorage?.getItem(STORAGE_KEY) ?? null;
    if (stored && VALID.test(stored)) id = stored;
  } catch {
    // Storage blocked: the id lives in memory for this page load.
  }
  if (!id) {
    id = generate();
    try {
      globalThis.sessionStorage?.setItem(STORAGE_KEY, id);
    } catch {
      // Ignore.
    }
  }
  cached = id;
  return id;
}

/** Test hook: forget the cached id. */
export function resetClientIdForTests() {
  cached = null;
}
