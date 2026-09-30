/** Tiny module store for the CSRF token. Set from `/api/v1/auth/state`, read by the client middleware. */
let token: string | null = null;

export const csrfStore = {
  get: (): string | null => token,
  set: (value: string | null | undefined): void => {
    token = value ?? null;
  },
};
