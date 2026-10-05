import { formatDistanceToNowStrict } from 'date-fns';
import { useState, type FormEvent } from 'react';
import { Dialog } from '../../components/ui/Dialog';
import { Field } from '../../components/ui/Field';
import { btnDanger, btnPrimary, btnSecondary } from '../../components/ui/classes';
import { describeError } from '../../lib/errors';
import { useShowBirthdays } from '../../lib/showBirthdays';
import {
  useConnectFelizAnniv,
  useDisconnectFelizAnniv,
  useFelizAnnivStatus,
  useSyncFelizAnniv,
} from '../birthdays/api';
import { SettingsSection } from './SettingsSection';

function ago(iso: string): string {
  return formatDistanceToNowStrict(new Date(iso), { addSuffix: true });
}

function birthdaysCount(n: number): string {
  return `${n} ${n === 1 ? 'birthday' : 'birthdays'}`;
}

/**
 * Settings › FelizAnniv birthdays: connect a FelizAnniv server (address + API key, tested by the
 * server before saving), sync now, disconnect, and show or hide birthdays on this device.
 * The API key is write-only: the field is never prefilled, only a short hint is shown.
 */
export function BirthdaysSection() {
  const status = useFelizAnnivStatus();
  const connect = useConnectFelizAnniv();
  const syncNow = useSyncFelizAnniv();
  const disconnect = useDisconnectFelizAnniv();
  const [show, setShow] = useShowBirthdays();
  // null = untouched: follow the saved address.
  const [url, setUrl] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [confirming, setConfirming] = useState(false);

  const data = status.data;
  const configured = !!data?.configured;
  const urlValue = url ?? data?.base_url ?? '';

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    syncNow.reset();
    connect.mutate(
      { base_url: urlValue.trim(), ...(apiKey ? { api_key: apiKey } : {}) },
      {
        onSuccess: () => {
          setApiKey('');
          setUrl(null);
        },
      },
    );
  };

  return (
    <SettingsSection title="FelizAnniv birthdays" id="birthdays">
      <p className="text-sm text-text-muted">
        Show the birthdays from your FelizAnniv app in the calendar. Hoje only reads names and
        birthdays (every 6 hours or when you sync); it never changes anything in FelizAnniv. Create
        a key in FelizAnniv under Settings › API Keys › New API Key (it starts with{' '}
        <code>fa_live_</code>).
      </p>

      {status.isError ? (
        <p role="alert" className="text-sm text-danger">
          {describeError(status.error)}
        </p>
      ) : null}

      {configured && data ? (
        <div className="space-y-1 text-sm">
          <p>
            Connected to <span className="break-all font-medium">{data.base_url}</span> with key{' '}
            <code>{data.api_key_hint}</code>.
          </p>
          <p role="status">
            {data.sync_pending
              ? 'Syncing…'
              : data.last_success_at
                ? `Last synced ${ago(data.last_success_at)} · ${birthdaysCount(data.count)}`
                : 'Not synced yet'}
          </p>
          {data.last_error ? (
            <p className="text-danger">
              Last sync failed
              {data.last_sync_at ? ` ${ago(data.last_sync_at)}` : ''}: {data.last_error}
            </p>
          ) : null}
        </div>
      ) : null}

      <form onSubmit={onSubmit} className="space-y-3" aria-label="FelizAnniv connection">
        <Field
          label="FelizAnniv address"
          name="felizanniv_url"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          required
          placeholder="https://felizanniv.example.com"
          value={urlValue}
          onChange={(e) => setUrl(e.target.value)}
          hint="The address you open FelizAnniv at, for example http://192.168.1.20:4000 on your network."
        />
        <Field
          label="API key"
          name="felizanniv_key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          required={!configured}
          minLength={8}
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={configured ? `Leave empty to keep ${data?.api_key_hint ?? 'the key'}` : ''}
          hint={configured ? 'Only needed to replace the saved key.' : undefined}
        />
        {connect.isError ? (
          <p role="alert" className="text-sm text-danger">
            {describeError(connect.error)}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className={btnPrimary} disabled={connect.isPending}>
            {connect.isPending ? 'Testing…' : 'Save & test'}
          </button>
          {configured ? (
            <>
              <button
                type="button"
                className={btnSecondary}
                disabled={syncNow.isPending || !!data?.sync_pending}
                onClick={() => {
                  connect.reset();
                  syncNow.mutate();
                }}
              >
                Sync now
              </button>
              <button type="button" className={btnDanger} onClick={() => setConfirming(true)}>
                Disconnect
              </button>
            </>
          ) : null}
        </div>
        {connect.isSuccess ? (
          <p role="status" className="text-sm">
            Connected. The birthdays appear after the first sync.
          </p>
        ) : null}
        {syncNow.isError ? (
          <p role="alert" className="text-sm text-danger">
            {describeError(syncNow.error)}
          </p>
        ) : null}
      </form>

      <label className="flex min-h-9 items-center gap-2 text-sm font-medium">
        <input
          type="checkbox"
          checked={show}
          onChange={(e) => setShow(e.target.checked)}
          className="size-4"
        />
        Show birthdays in the calendar (on this device)
      </label>

      {confirming ? (
        <Dialog title="Disconnect FelizAnniv?" onClose={() => setConfirming(false)}>
          <p className="text-sm">
            This removes the saved address and key and the {birthdaysCount(data?.count ?? 0)} synced
            to Hoje. Nothing changes in FelizAnniv.
          </p>
          {disconnect.isError ? (
            <p role="alert" className="mt-2 text-sm text-danger">
              {describeError(disconnect.error)}
            </p>
          ) : null}
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              className={btnDanger}
              disabled={disconnect.isPending}
              onClick={() =>
                disconnect.mutate(undefined, {
                  onSuccess: () => {
                    setConfirming(false);
                    setUrl(null);
                    connect.reset();
                  },
                })
              }
            >
              Disconnect
            </button>
            <button type="button" className={btnSecondary} onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </div>
        </Dialog>
      ) : null}
    </SettingsSection>
  );
}
