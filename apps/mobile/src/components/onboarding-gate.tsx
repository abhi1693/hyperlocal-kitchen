import { ActivityIndicator, Button, HelperText } from "react-native-paper";
import { Screen } from "./screen";
import { useAuth } from "../auth/provider";
import { useOnboarding } from "../onboarding/provider";

export function OnboardingGate() {
  const { signOut, busy, error: authError } = useAuth();
  const { loading, error, refresh } = useOnboarding();
  return (
    <Screen
      title="Finding your community"
      subtitle="We’re checking whether you’ve already joined a community."
    >
      {loading && !error && <ActivityIndicator accessibilityLabel="Loading community" />}
      {error && (
        <>
          <HelperText type="error" visible accessibilityLiveRegion="polite">
            {error}
          </HelperText>
          <Button
            mode="contained"
            onPress={() => void refresh()}
            disabled={loading}
            loading={loading}
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
