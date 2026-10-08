import { useState } from "react";
import { Button, Card, HelperText, Icon, Text } from "react-native-paper";
import type { ExperienceUpdateMode } from "../api/generated";
import { AuthError } from "../auth/client";
import { useAuth } from "../auth/provider";
import { Screen } from "../components/screen";
import { useExperience } from "../experience/provider";
import { useOnboarding } from "../onboarding/provider";

export default function ChooseExperienceScreen() {
  const { chooseMode, saving } = useExperience();
  const { state } = useOnboarding();
  const { signOut, busy, error: authError } = useAuth();
  const [selected, setSelected] = useState<ExperienceUpdateMode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const choose = async (mode: ExperienceUpdateMode) => {
    if (saving || busy) return;
    setSelected(mode);
    setError(null);
    try {
      await chooseMode(mode);
    } catch (reason) {
      setError(
        reason instanceof AuthError
          ? reason.message
          : "Could not save your choice. Please try again.",
      );
    }
  };
  return (
    <Screen
      title="What brings you here?"
      subtitle={
        "You’ve joined " +
        (state?.membership?.community_name ?? "your community") +
        ". Choose how you’d like to get started."
      }
    >
      <Card mode="outlined">
        <Card.Content style={{ gap: 16 }}>
          <Icon source="silverware-fork-knife" size={40} />
          <Text variant="titleLarge">Order meals</Text>
          <Text variant="bodyLarge">Enjoy food made by kitchens in your community.</Text>
          <Button
            mode="contained"
            disabled={saving || busy}
            loading={saving && selected === "customer"}
            onPress={() => void choose("customer")}
          >
            Find meals
          </Button>
        </Card.Content>
      </Card>
      <Card mode="outlined">
        <Card.Content style={{ gap: 16 }}>
          <Icon source="chef-hat" size={40} />
          <Text variant="titleLarge">Run a kitchen</Text>
          <Text variant="bodyLarge">
            Set up your kitchen, add dishes, and prepare your daily menus.
          </Text>
          <Button
            mode="contained"
            disabled={saving || busy}
            loading={saving && selected === "kitchen_owner"}
            onPress={() => void choose("kitchen_owner")}
          >
            Set up my kitchen
          </Button>
        </Card.Content>
      </Card>
      <Text variant="bodyMedium">
        Kitchen owners can order meals too. You can change your choice in Account.
      </Text>
      {(error || authError) && (
        <HelperText type="error" visible accessibilityLiveRegion="polite">
          {error ?? authError}
        </HelperText>
      )}
      <Button disabled={saving || busy} loading={busy} onPress={() => void signOut()}>
        Sign out
      </Button>
    </Screen>
  );
}
