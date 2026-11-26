import { useEffect, useRef, type ChangeEvent } from 'react';
import { btnPrimary, btnSecondary } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { useCategories } from '../categories/api';
import { ImportPreview } from './ImportPreview';
import { summary } from './importCommon';
import { MAX_CATEGORY_LENGTH, useIcsImport } from './useIcsImport';

/**
 * Settings › Your data › Import a calendar file: adds the events of an .ics file (Google
 * Calendar, Outlook, Apple Calendar, ...) to one category. Always a merge, previewed first.
 */
export function IcsImportPanel() {
  const categories = useCategories();
  const flow = useIcsImport();
  const { file, preview, done, valid, current } = flow;
  const fileInput = useRef<HTMLInputElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const resultBox = useRef<HTMLDivElement>(null);
  const focusPreview = useRef(false);

  useEffect(() => {
    if (preview && focusPreview.current) {
      focusPreview.current = false;
      previewHeading.current?.focus();
    }
  }, [preview]);
  useEffect(() => {
    if (done) resultBox.current?.focus();
  }, [done]);

  const clearInput = () => {
    if (fileInput.current) fileInput.current.value = '';
  };

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    if (!chosen) return;
    if (await flow.chooseFile(chosen)) focusPreview.current = true;
    else clearInput();
  };

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Import a calendar file</h3>
      <p className="text-sm text-text-muted">
        Add the events of an .ics file exported from Google Calendar, Outlook, Apple Calendar and
        similar. They all go into one category, and events you already have are skipped, so
        importing a file twice is safe. Repeats other than weekly, every two weeks, monthly or
        yearly are added as separate events from five years back to two years ahead.
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
      <FormError
        message={flow.fileError ?? (flow.checkError ? describeError(flow.checkError) : null)}
      />

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
            value={flow.category}
            onChange={(e) => flow.setCategory(e.target.value)}
            hint="Pick one of yours, or type a new name to create it."
            error={valid ? undefined : `Enter 1 to ${MAX_CATEGORY_LENGTH} characters.`}
          />
          <datalist id="ics-category-names">
            {(categories.data ?? []).map((c) => (
              <option key={c.id} value={c.name} />
            ))}
          </datalist>
          {flow.checking && !preview ? (
            <p role="status" className="text-sm text-text-muted">
              Checking {file.name}…
            </p>
          ) : null}
          {preview ? <ImportPreview result={preview.result} eventsOnly /> : null}
          <FormError message={flow.importError ? describeError(flow.importError) : null} />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className={btnPrimary}
              disabled={flow.importing || !valid || !current}
              onClick={() => {
                clearInput();
                flow.submit();
              }}
            >
              Import
            </button>
            <button
              type="button"
              className={btnSecondary}
              onClick={() => {
                clearInput();
                flow.reset();
              }}
            >
              Cancel
            </button>
            <span role="status" className="text-sm text-text-muted">
              {flow.importing ? 'Importing…' : null}
            </span>
          </div>
        </section>
      ) : null}
    </div>
  );
}
