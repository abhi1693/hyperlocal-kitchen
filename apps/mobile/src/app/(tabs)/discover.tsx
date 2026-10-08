import { router } from "expo-router";
import { Button, Card, Icon, Text } from "react-native-paper";
import { Screen } from "../../components/screen";
import { useOnboarding } from "../../onboarding/provider";
export default function DiscoverScreen() {
  const { state } = useOnboarding();
  return (
    <Screen
      title="Good food, closer to home"
      subtitle="Discover meals made by kitchens in your community."
    >
      <Card mode="contained">
        <Card.Content style={{ gap: 16 }}>
          <Icon source="home-heart" size={48} />
          <Text variant="titleLarge">
            {state?.membership?.community_name ?? "Your neighbourhood, your table"}
          </Text>
          <Text variant="bodyMedium">
            Your community’s kitchens and daily menus will appear here as they become available.
          </Text>
          <Button mode="contained" onPress={() => router.navigate("/account")}>
            Your account
          </Button>
        </Card.Content>
      </Card>
      <Text variant="bodyMedium">
        A place for home cooking, familiar flavours, and food made nearby.
      </Text>
    </Screen>
  );
}
