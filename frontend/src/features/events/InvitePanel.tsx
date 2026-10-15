import { useState, type KeyboardEvent } from 'react';
import { btnSecondary, inputClass } from '../../components/ui/classes';
import { Field } from '../../components/ui/Field';
import { FormError } from '../../components/ui/FormError';
import { describeError } from '../../lib/errors';
import { useEmailSettings } from '../settings/api';
import { useInvites, useSendInvite } from './api';

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_MESSAGE_LENGTH = 500;

const when = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' });

/**
 * Email the saved event to one person and list everyone it was sent to before. It sits inside
 * the event form, so Enter in its fields sends the invitation instead of saving the event.
 */
export function InvitePanel({ eventId }: { eventId: string }) {
  const invites = useInvites(eventId);
  const send = useSendInvite(eventId);
  const emailSettings = useEmailSettings();
  const emailMissing = emailSettings.data?.configured === false;

  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  const submit = async () => {
    const address = email.trim();
    setSentTo(null);
    if (!EMAIL_SHAPE.test(address)) {
      setError('Enter a valid email address.');
      return;
    }
    setError(null);
    try {
      await send.mutateAsync({ email: address, message: message.trim() || null });
      setSentTo(address);
      setEmail('');
      setMessage('');
    } catch (e) {
      setError(
        describeError(e, {
          502: 'The mail server could not deliver the invitation.',
          503: 'Email is not configured on this server.',
        }),
      );
    }
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    if (!send.isPending) void submit();
  };

  return (
    <section aria-labelledby="event-invite-heading" className="space-y-2">
      <h3 id="event-invite-heading" className="text-sm font-medium">
        Invite by email
      </h3>
      <Field
        label="Email address"
        type="email"
        name="invitee"
        autoComplete="off"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        onKeyDown={onKeyDown}
        maxLength={254}
        hint={
          emailMissing
            ? 'Email is not set up on the server, so invitations cannot be sent.'
            : 'Sends the saved event with a calendar file attached. Replies come to you.'
        }
      />
      <div className="space-y-1">
        <label htmlFor="event-invite-message" className="block text-sm font-medium">
          Message (optional)
        </label>
        <textarea
          id="event-invite-message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={2}
          maxLength={MAX_MESSAGE_LENGTH}
          className={`${inputClass} py-2`}
        />
      </div>
      <FormError message={error} />
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={btnSecondary}
          disabled={send.isPending || emailMissing}
          onClick={() => void submit()}
        >
          Send invitation
        </button>
        <span role="status" className="text-sm text-text-muted">
          {send.isPending ? 'Sending…' : sentTo ? `Invitation sent to ${sentTo}.` : null}
        </span>
      </div>
      {invites.data && invites.data.length > 0 ? (
        <div>
          <p className="text-xs font-medium text-text-muted">Invitations sent</p>
          <ul className="mt-1 space-y-1 text-sm">
            {invites.data.map((invite) => (
              <li key={invite.id} className="flex flex-wrap gap-x-2">
                <span className="break-all">{invite.email}</span>
                <span className="text-text-muted">
                  {invite.status === 'sent' ? '' : 'not delivered, '}
                  {when.format(new Date(invite.created_at))}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
