import { Card, Text } from "react-native-paper";
import { Screen } from "../../components/screen";
export default function AccountScreen() {
  return (
    <Screen
      title="Make yourself at home"
      subtitle="One account for enjoying meals and managing your kitchen."
    >
      <Card mode="outlined">
        <Card.Content style={{ gap: 16 }}>
          <Text variant="titleMedium">Sign-in is coming next</Text>
          <Text variant="bodyMedium">
            This first version introduces the app. Sign-in, community selection, and your kitchen
            workspace will follow.
          </Text>
        </Card.Content>
      </Card>
    </Screen>
  );
}
