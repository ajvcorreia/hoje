import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/client';
import { btnDanger, btnPrimary, btnSecondary } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import {
  MAX_IMPORT_BYTES,
  useExportData,
  useImportData,
  type ImportMode,
  type ImportResult,
} from './dataApi';
import { SettingsSection } from './SettingsSection';

const MB = 1_000_000;

function readText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('read failed'));
    reader.readAsText(file);
  });
}

function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

function ExportPanel() {
  const exportData = useExportData();
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Export</h3>
      <p className="text-sm text-text-muted">
        Download your categories, events (with reminders), leave allowances, holiday calendar
        settings, time zone and weekend days as one JSON file. Passwords, two-factor secrets,
        recovery codes and sessions are never included.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={btnSecondary}
          disabled={exportData.isPending}
          onClick={() => exportData.mutate()}
        >
          Export my data
        </button>
        <span role="status" className="text-sm text-text-muted">
          {exportData.isSuccess ? `Downloaded ${exportData.data}` : null}
        </span>
      </div>
      <FormError message={exportData.isError ? describeError(exportData.error) : null} />
    </div>
  );
}

function Preview({ result }: { result: ImportResult }) {
  const { categories, events, leave_policies: leave, holiday_calendars: calendars } = result;
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-text-muted">Categories</dt>
        <dd>
          {categories.create} new, {categories.reuse} matched to existing
        </dd>
        <dt className="text-text-muted">Events</dt>
        <dd>
          {events.create} to add, {events.skip_duplicate} already there (skipped)
        </dd>
        <dt className="text-text-muted">Leave allowances</dt>
        <dd>
          {leave.create} new, {leave.update} updated
        </dd>
        <dt className="text-text-muted">Holiday calendars</dt>
        <dd>{calendars.update} updated</dd>
        <dt className="text-text-muted">Time zone and weekend</dt>
        <dd>{result.settings.update ? 'will be updated' : 'unchanged'}</dd>
      </dl>
      {result.warnings.length > 0 ? (
        <ul aria-label="Warnings" className="list-disc space-y-1 pl-5 text-sm">
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function summary(result: ImportResult): string {
  const added = `${plural(result.events.create, 'event', 'events')} and ${plural(result.categories.create, 'category', 'categories')} added`;
  const skipped =
    result.events.skip_duplicate > 0
      ? `, ${plural(result.events.skip_duplicate, 'duplicate', 'duplicates')} skipped`
      : '';
  return `Import finished: ${added}${skipped}.`;
}

function ImportPanel() {
  const qc = useQueryClient();
  const dryRun = useImportData();
  const run = useImportData();
  const fileInput = useRef<HTMLInputElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const resultBox = useRef<HTMLDivElement>(null);

  const [file, setFile] = useState<{ name: string; data: Record<string, unknown> } | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [mode, setMode] = useState<ImportMode>('merge');
  const [previews, setPreviews] = useState<Partial<Record<ImportMode, ImportResult>>>({});
  const [password, setPassword] = useState('');
  const [done, setDone] = useState<ImportResult | null>(null);

  const preview = previews[mode];
  const hasPreview = preview !== undefined;
  // The first (merge) preview keeps the card on screen while another mode is being checked.
  const shown = preview ?? previews.merge;
  useEffect(() => {
    if (hasPreview) previewHeading.current?.focus();
  }, [file, hasPreview]);
  useEffect(() => {
    if (done) resultBox.current?.focus();
  }, [done]);

  const reset = () => {
    setFile(null);
    setFileError(null);
    setMode('merge');
    setPreviews({});
    setPassword('');
    dryRun.reset();
    run.reset();
    if (fileInput.current) fileInput.current.value = '';
  };

  const preflight = (data: Record<string, unknown>, which: ImportMode) => {
    dryRun.mutate(
      { mode: which, dry_run: true, data },
      { onSuccess: (result) => setPreviews((prev) => ({ ...prev, [which]: result })) },
    );
  };

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    if (!chosen) return;
    setDone(null);
    reset();
    if (chosen.size > MAX_IMPORT_BYTES) {
      setFileError(
        `This file is ${(chosen.size / MB).toFixed(1)} MB. Files over 10 MB cannot be imported.`,
      );
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(await readText(chosen));
    } catch {
      setFileError('This file is not valid JSON. Choose a file exported from Hoje.');
      return;
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      setFileError('This is not a Hoje export file.');
      return;
    }
    const data = parsed as Record<string, unknown>;
    setFile({ name: chosen.name, data });
    preflight(data, 'merge');
  };

  const chooseMode = (next: ImportMode) => {
    setMode(next);
    run.reset();
    if (file && !previews[next]) preflight(file.data, next);
  };

  const submit = () => {
    if (!file || !preview) return;
    run.mutate(
      {
        mode,
        dry_run: false,
        data: file.data,
        ...(mode === 'replace' ? { password } : {}),
      },
      {
        onSuccess: (result) => {
          reset();
          setDone(result);
          void qc.invalidateQueries();
        },
      },
    );
  };

  const importError =
    run.error instanceof ApiError && run.error.status === 400
      ? 'Incorrect password.'
      : run.isError
        ? describeError(run.error)
        : null;
  const checking = file !== null && !hasPreview && dryRun.isPending;
  const previewError = file !== null && !hasPreview && dryRun.isError;

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Import</h3>
      <p className="text-sm text-text-muted">
        Load an export file made by Hoje. You see what would change before anything is written.
      </p>
      <input
        ref={fileInput}
        type="file"
        accept=".json,application/json"
        aria-label="Export file to import"
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => void onFile(e)}
      />
      <button type="button" className={btnSecondary} onClick={() => fileInput.current?.click()}>
        Import…
      </button>
      <FormError message={fileError ?? (previewError ? describeError(dryRun.error) : null)} />

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

      {checking ? (
        <p role="status" className="text-sm text-text-muted">
          Checking {file.name}…
        </p>
      ) : null}

      {file && shown ? (
        <section
          aria-labelledby="import-preview-heading"
          className="space-y-3 rounded-md border border-border p-3"
        >
          <h4
            id="import-preview-heading"
            ref={previewHeading}
            tabIndex={-1}
            className="text-sm font-semibold outline-none"
          >
            {`What importing ${file.name} would do`}
          </h4>
          <Preview result={shown} />
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Import mode</legend>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name="import-mode"
                className="mt-1 size-4"
                checked={mode === 'merge'}
                onChange={() => chooseMode('merge')}
              />
              <span>
                <span className="font-medium">Merge</span>: add the file to what you have.
                Categories with the same name are reused and duplicate events are skipped.
              </span>
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name="import-mode"
                className="mt-1 size-4"
                checked={mode === 'replace'}
                onChange={() => chooseMode('replace')}
              />
              <span>
                <span className="font-medium">Replace</span>: use the file instead of what you have.
              </span>
            </label>
          </fieldset>
          {mode === 'replace' ? (
            <div className="space-y-3">
              <p className="text-sm font-medium text-danger">
                Your current events and categories will be moved to the bin first.
              </p>
              <Field
                label="Your password"
                type="password"
                name="import_password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                hint="Needed to confirm replacing your data."
                required
              />
            </div>
          ) : null}
          <FormError message={importError} />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className={mode === 'replace' ? btnDanger : btnPrimary}
              disabled={run.isPending || (mode === 'replace' && password === '')}
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

/** Settings › Your data: export everything, or import an export file (merge or replace). */
export function DataSection() {
  return (
    <SettingsSection title="Your data" id="data">
      <ExportPanel />
      <ImportPanel />
    </SettingsSection>
  );
}
