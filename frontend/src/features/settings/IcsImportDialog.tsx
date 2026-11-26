import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { btnPrimary, btnSecondary } from '../../components/ui/classes';
import { Dialog } from '../../components/ui/Dialog';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { useCategories } from '../categories/api';
import { MAX_ICS_BYTES } from './dataApi';
import { MB, plural, summary } from './importCommon';
import { ImportPreview } from './ImportPreview';
import { MAX_CATEGORY_LENGTH, useIcsImport } from './useIcsImport';

const TITLE = 'Import a calendar file';
const CATEGORY_ID = 'ics-dialog-category';

function ImportIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className="size-4 shrink-0"
    >
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  );
}

function CalendarIcon({ className }: { className: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${className}`}
    >
      <rect x="3" y="4" width="18" height="17" rx="2" />
      <path d="M3 9h18M8 2v4M16 2v4" />
    </svg>
  );
}

/**
 * The calendar's Import button and the window it opens. `compact` shows only the icon (phone
 * header); otherwise the label shows from wide screens up.
 */
export function ImportIcsButton({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-label={TITLE}
        title={TITLE}
        className={`${btnSecondary} gap-1.5`}
        onClick={() => setOpen(true)}
      >
        <ImportIcon />
        {compact ? null : <span className="hidden lg:inline">Import</span>}
      </button>
      {open ? <IcsImportDialog onClose={() => setOpen(false)} /> : null}
    </>
  );
}

/** Pick a calendar file, check what it would add, import it: the Settings import in a window. */
export function IcsImportDialog({ onClose }: { onClose: () => void }) {
  const categories = useCategories();
  const flow = useIcsImport();
  const { file, preview, done, valid, current } = flow;
  const fileInput = useRef<HTMLInputElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (file) document.getElementById(CATEGORY_ID)?.focus();
  }, [file]);
  useEffect(() => {
    if (done) closeButton.current?.focus();
  }, [done]);

  const choose = (chosen: File | undefined) => {
    if (fileInput.current) fileInput.current.value = '';
    if (chosen) void flow.chooseFile(chosen);
  };
  const onFile = (event: ChangeEvent<HTMLInputElement>) => choose(event.target.files?.[0]);
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  };
  const pick = () => fileInput.current?.click();
  const adding = current && preview ? preview.result.events.create : null;

  return (
    <Dialog title={TITLE} onClose={onClose}>
      <input
        ref={fileInput}
        type="file"
        accept=".ics,text/calendar"
        aria-label="Calendar file to import"
        className="sr-only"
        tabIndex={-1}
        onChange={onFile}
      />
      {done ? (
        <div className="space-y-4">
          <div
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
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className={btnSecondary} onClick={flow.clearDone}>
              Import another
            </button>
            <button ref={closeButton} type="button" className={btnPrimary} onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      ) : file ? (
        <div className="space-y-4" aria-busy={!current}>
          <div className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
            <CalendarIcon className="size-4 text-accent" />
            <span className="min-w-0 flex-1 break-words font-medium">{file.name}</span>
            <button type="button" className="text-accent hover:underline" onClick={pick}>
              Change
            </button>
          </div>
          <Field
            id={CATEGORY_ID}
            label="Add the events to this category"
            name="ics_dialog_category"
            list="ics-dialog-category-names"
            maxLength={MAX_CATEGORY_LENGTH}
            value={flow.category}
            onChange={(e) => flow.setCategory(e.target.value)}
            hint="Pick one of yours, or type a new name to create it."
            error={valid ? undefined : `Enter 1 to ${MAX_CATEGORY_LENGTH} characters.`}
          />
          <datalist id="ics-dialog-category-names">
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
          <FormError
            message={
              flow.checkError
                ? describeError(flow.checkError)
                : flow.importError
                  ? describeError(flow.importError)
                  : null
            }
          />
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span role="status" className="mr-auto text-sm text-text-muted">
              {flow.importing ? 'Importing…' : null}
            </span>
            <button type="button" className={btnSecondary} onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className={btnPrimary}
              disabled={flow.importing || !valid || !current}
              onClick={flow.submit}
            >
              {adding === null ? 'Import' : `Import ${plural(adding, 'event', 'events')}`}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-text-muted">
            Add the events of an .ics file from Google Calendar, Outlook, Apple Calendar and
            similar. Events you already have are skipped, so importing a file twice is safe.
          </p>
          <button
            type="button"
            data-autofocus
            onClick={pick}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex w-full flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm ${
              dragging ? 'border-accent bg-surface' : 'border-border-strong bg-surface-muted'
            }`}
          >
            <CalendarIcon className="size-7 text-text-muted" />
            <span>
              <span className="font-semibold">Choose an .ics file</span> or drop it here
            </span>
            <span className="text-xs text-text-muted">Up to {MAX_ICS_BYTES / MB} MB</span>
          </button>
          <FormError message={flow.fileError} />
          <div className="flex justify-end">
            <button type="button" className={btnSecondary} onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
