import { useState } from 'react';
import { btnPrimary, btnSecondary } from '../../components/ui/classes';

/** Copies text to the clipboard; the label flips to "Copied" for feedback. */
export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={btnSecondary}
      onClick={() => {
        void (async () => {
          try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
          } catch {
            setCopied(false);
          }
        })();
      }}
    >
      {copied ? 'Copied' : label}
    </button>
  );
}

function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Shows recovery codes once; "Done" stays disabled until the user confirms they saved them. */
export function RecoveryCodesPanel({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [saved, setSaved] = useState(false);
  const text = codes.join('\n') + '\n';
  return (
    <div className="space-y-4">
      <p className="text-sm">
        Save these recovery codes somewhere safe. Each one works once if you lose your
        authenticator. They will not be shown again.
      </p>
      <ul
        aria-label="Recovery codes"
        className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-md border border-border bg-surface-muted p-3 font-mono text-sm"
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
      <div className="flex gap-2">
        <CopyButton text={text} />
        <button
          type="button"
          className={btnSecondary}
          onClick={() => downloadText('hoje-recovery-codes.txt', text)}
        >
          Download .txt
        </button>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={saved}
          onChange={(e) => setSaved(e.target.checked)}
          className="size-4"
        />
        I&apos;ve saved these codes
      </label>
      <button type="button" className={btnPrimary} disabled={!saved} onClick={onDone}>
        Done
      </button>
    </div>
  );
}
