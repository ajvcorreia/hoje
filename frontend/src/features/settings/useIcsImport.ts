import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { MAX_ICS_BYTES, useImportIcs, type ImportResult } from './dataApi';
import { MB, readText } from './importCommon';

export const DEFAULT_CATEGORY = 'Imported';
export const MAX_CATEGORY_LENGTH = 40;
const CHECK_DELAY_MS = 400;

export interface IcsFile {
  name: string;
  text: string;
}

/**
 * The state of importing one calendar file: the chosen file, the category, a dry-run preview kept
 * in step with them, and the import itself. Shared by Settings › Your data and the calendar's
 * Import window.
 */
export function useIcsImport() {
  const qc = useQueryClient();
  const dryRun = useImportIcs();
  const run = useImportIcs();
  const latestCheck = useRef(0);
  const hasPreview = useRef(false);

  const [file, setFile] = useState<IcsFile | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [category, setCategory] = useState(DEFAULT_CATEGORY);
  const [preview, setPreview] = useState<{ category: string; result: ImportResult } | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);

  const wanted = category.trim();
  const valid = wanted.length > 0 && wanted.length <= MAX_CATEGORY_LENGTH;
  const current = preview !== null && preview.category === wanted;

  useEffect(() => {
    hasPreview.current = preview !== null;
  }, [preview]);

  // Check the file against the chosen category: at once for a new file, shortly after typing.
  const { mutate: check } = dryRun;
  const text = file?.text;
  useEffect(() => {
    if (text === undefined || !valid) return;
    const ticket = ++latestCheck.current;
    const timer = setTimeout(
      () =>
        check(
          { ics: text, category: wanted, dry_run: true },
          {
            onSuccess: (result) => {
              if (ticket === latestCheck.current) setPreview({ category: wanted, result });
            },
          },
        ),
      hasPreview.current ? CHECK_DELAY_MS : 0,
    );
    return () => clearTimeout(timer);
  }, [text, wanted, valid, check]);

  /** Back to no file chosen; a finished import's result stays until a new file is chosen. */
  const reset = () => {
    latestCheck.current++;
    setFile(null);
    setFileError(null);
    setCategory(DEFAULT_CATEGORY);
    setPreview(null);
    dryRun.reset();
    run.reset();
  };

  /** Reads a chosen file; true when it is a calendar file now waiting for its preview. */
  const chooseFile = async (chosen: File): Promise<boolean> => {
    setDone(null);
    reset();
    if (chosen.size > MAX_ICS_BYTES) {
      setFileError(
        `This file is ${(chosen.size / MB).toFixed(1)} MB. Calendar files over ${MAX_ICS_BYTES / MB} MB cannot be imported.`,
      );
      return false;
    }
    let content: string;
    try {
      content = await readText(chosen);
    } catch {
      setFileError('This file could not be read.');
      return false;
    }
    if (!/BEGIN:VCALENDAR/i.test(content)) {
      setFileError('This is not an iCalendar (.ics) file.');
      return false;
    }
    setFile({ name: chosen.name, text: content });
    return true;
  };

  const submit = () => {
    if (!file || !current) return;
    run.mutate(
      { ics: file.text, category: wanted, dry_run: false },
      {
        onSuccess: (result) => {
          reset();
          setDone(result);
          void qc.invalidateQueries();
        },
      },
    );
  };

  return {
    file,
    fileError,
    category,
    setCategory,
    valid,
    current,
    preview,
    done,
    clearDone: () => setDone(null),
    checking: file !== null && valid && !current && dryRun.isPending,
    checkError: file !== null && !current && dryRun.isError ? dryRun.error : null,
    importing: run.isPending,
    importError: run.isError ? run.error : null,
    chooseFile,
    reset,
    submit,
  };
}
