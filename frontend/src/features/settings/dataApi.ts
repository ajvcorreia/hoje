import { useMutation } from '@tanstack/react-query';
import { api, unwrap } from '../../api/client';
import type { components } from '../../api/schema';

export type ImportRequest = components['schemas']['ImportRequest'];
export type ImportResult = components['schemas']['ImportResult'];
export type ImportMode = ImportRequest['mode'];

/**
 * Largest file the client will send. The server accepts 10 MiB and Caddy 10 MB (10 000 000
 * bytes), measured on the whole request; keep a margin for the JSON envelope around the file.
 */
export const MAX_IMPORT_BYTES = 10_000_000 - 1_000;

function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** The file name from `Content-Disposition`, reduced to harmless characters. */
export function exportFilename(response: Response): string {
  const header = response.headers.get('content-disposition') ?? '';
  const match = /filename="?([^";]+)"?/i.exec(header);
  const name = match?.[1]?.replace(/[^A-Za-z0-9._-]/g, '_');
  return name && name !== '.' && name !== '..' ? name : `hoje-export-${todayIso()}.json`;
}

/** Hands a Blob to the browser as a file download, then frees the object URL. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function useExportData() {
  return useMutation({
    meta: { protected: true },
    mutationFn: async () => {
      const result = await api.GET('/api/v1/export', { parseAs: 'blob' });
      const blob = unwrap(result);
      const filename = exportFilename(result.response);
      saveBlob(blob, filename);
      return filename;
    },
  });
}

export function useImportData() {
  return useMutation({
    meta: { protected: true },
    mutationFn: async (body: ImportRequest): Promise<ImportResult> =>
      unwrap(await api.POST('/api/v1/import', { body })),
  });
}
