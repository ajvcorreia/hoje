import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { btnPrimary, btnSecondary } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { useCategories } from '../categories/api';
import { MAX_ICS_BYTES, useImportIcs, type ImportResult } from './dataApi';
import { ImportPreview } from './ImportPreview';
import { MB, readText, summary } from './importCommon';

const DEFAULT_CATEGORY = 'Imported';
const MAX_CATEGORY_LENGTH = 40;
const CHECK_DELAY_MS = 400;

interface IcsFile {
  name: string;
  text: string;
}

/**
 * Settings › Your data › Import a calendar file: adds the events of an .ics file (Google
 * Calendar, Outlook, Apple Calendar, ...) to one category. Always a merge, previewed first.
 */
export function IcsImportPanel() {
  const qc = useQueryClient();
  const categories = useCategories();
  const dryRun = useImportIcs();
  const run = useImportIcs();
  const fileInput = useRef<HTMLInputElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const resultBox = useRef<HTMLDivElement>(null);
  const latestCheck = useRef(0);
  const focusPreview = useRef(false);
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
    if (preview && focusPreview.current) {
      focusPreview.current = false;
      previewHeading.current?.focus();
    }
  }, [preview]);
  useEffect(() => {
    if (done) resultBox.current?.focus();
  }, [done]);

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

  const reset = () => {
    latestCheck.current++;
    setFile(null);
    setFileError(null);
    setCategory(DEFAULT_CATEGORY);
    setPreview(null);
    dryRun.reset();
    run.reset();
    if (fileInput.current) fileInput.current.value = '';
  };

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    if (!chosen) return;
    setDone(null);
    reset();
    if (chosen.size > MAX_ICS_BYTES) {
      setFileError(
        `This file is ${(chosen.size / MB).toFixed(1)} MB. Calendar files over ${MAX_ICS_BYTES / MB} MB cannot be imported.`,
      );
      return;
    }
    let content: string;
    try {
      content = await readText(chosen);
    } catch {
      setFileError('This file could not be read.');
      return;
    }
    if (!/BEGIN:VCALENDAR/i.test(content)) {
      setFileError('This is not an iCalendar (.ics) file.');
      return;
    }
    focusPreview.current = true;
    setFile({ name: chosen.name, text: content });
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

  const checking = file !== null && valid && !current && dryRun.isPending;
  const checkError = file !== null && !current && dryRun.isError;

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Import a calendar file</h3>
      <p className="text-sm text-text-muted">
        Add the events of an .ics file exported from Google Calendar, Outlook, Apple Calendar and
        similar. They all go into one category, and events you already have are skipped, so
        importing a file twice is safe. Repeats other than monthly or yearly are added as separate
        events from five years back to two years ahead.
      </p>
      <input
        ref={fileInput}
        type="file"
        accept=".ics,text/calendar"
        aria-label="Calendar file to import"
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => void onFile(e)}
      />
      <button type="button" className={btnSecondary} onClick={() => fileInput.current?.click()}>
        Import calendar…
      </button>
      <FormError message={fileError ?? (checkError ? describeError(dryRun.error) : null)} />

      {done ? (
        <div
          ref={resultBox}
          tabIndex={-1}
          role="status"
          className="space-y-1 rounded-md border border-border px-3 py-2 text-sm"
        >
          <p className="font-medium">{summary(done)}</p>
          {done.warnings.map((warning) => (
            <p key={warning} className="text-text-muted">
              {warning}
            </p>
          ))}
        </div>
      ) : null}

      {file ? (
        <section
          aria-labelledby="ics-preview-heading"
          aria-busy={!current}
          className="space-y-3 rounded-md border border-border p-3"
        >
          <h4
            id="ics-preview-heading"
            ref={previewHeading}
            tabIndex={-1}
            className="text-sm font-semibold outline-none"
          >
            {`What importing ${file.name} would do`}
          </h4>
          <Field
            label="Add the events to this category"
            name="ics_category"
            list="ics-category-names"
            maxLength={MAX_CATEGORY_LENGTH}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            hint="Pick one of yours, or type a new name to create it."
            error={valid ? undefined : `Enter 1 to ${MAX_CATEGORY_LENGTH} characters.`}
          />
          <datalist id="ics-category-names">
            {(categories.data ?? []).map((c) => (
              <option key={c.id} value={c.name} />
            ))}
          </datalist>
          {checking && !preview ? (
            <p role="status" className="text-sm text-text-muted">
              Checking {file.name}…
            </p>
          ) : null}
          {preview ? <ImportPreview result={preview.result} eventsOnly /> : null}
          <FormError message={run.isError ? describeError(run.error) : null} />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className={btnPrimary}
              disabled={run.isPending || !valid || !current}
              onClick={submit}
            >
              Import
            </button>
            <button type="button" className={btnSecondary} onClick={reset}>
              Cancel
            </button>
            <span role="status" className="text-sm text-text-muted">
              {run.isPending ? 'Importing…' : null}
            </span>
          </div>
        </section>
      ) : null}
    </div>
  );
}
