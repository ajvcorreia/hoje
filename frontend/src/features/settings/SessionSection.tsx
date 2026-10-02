import { btnSecondary } from '../../components/ui/classes';
import { useLogout } from '../auth/api';
import { SettingsSection } from './SettingsSection';

export function SessionSection() {
  const logout = useLogout();
  return (
    <SettingsSection title="Session">
      <button
        type="button"
        className={btnSecondary}
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
      >
        Log out
      </button>
    </SettingsSection>
  );
}
