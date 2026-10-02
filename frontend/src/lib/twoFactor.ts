/** Groups a TOTP secret into blocks of four characters for easier manual entry. */
export function groupSecret(secret: string): string {
  return secret.replace(/\s+/g, '').replace(/(.{4})(?=.)/g, '$1 ');
}

/** Encodes SVG markup as a data URI so it can be shown in an <img> (never injected as HTML). */
export function svgDataUri(svg: string): string {
  let encoded: string;
  try {
    encoded = btoa(svg);
  } catch {
    // Non-Latin1 characters: encode as UTF-8 first.
    const bytes = new TextEncoder().encode(svg);
    encoded = btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(''));
  }
  return 'data:image/svg+xml;base64,' + encoded;
}
