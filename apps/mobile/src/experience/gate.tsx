import { ActivityIndicator, Button, HelperText } from "react-native-paper";
import { Screen } from "../components/screen";
import { useAuth } from "../auth/provider";
import { useExperience } from "./provider";

export function ExperienceGate() {
  const { signOut, busy, error: authError } = useAuth();
  const { loading, error, refresh } = useExperience();
  return (
    <Screen
      title="Getting your account ready"
      subtitle="We’re loading your meal and kitchen settings."
    >
      {loading && !error && <ActivityIndicator accessibilityLabel="Loading account settings" />}
      {error && (
        <>
          <HelperText type="error" visible accessibilityLiveRegion="polite">
            {error}
          </HelperText>
          <Button
            mode="contained"
            loading={loading}
            disabled={loading}
            onPress={() => void refresh().catch(() => undefined)}
          >
            Try again
          </Button>
        </>
      )}
      {authError && (
        <HelperText type="error" visible>
          {authError}
        </HelperText>
      )}
      <Button disabled={busy} loading={busy} onPress={() => void signOut()}>
        Sign out
      </Button>
    </Screen>
  );
}
