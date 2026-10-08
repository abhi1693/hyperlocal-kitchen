import { Button, Card, HelperText, Text } from "react-native-paper";
import { Screen } from "../../components/screen";
import { useAuth } from "../../auth/provider";
export default function AccountScreen() {
  const { user, signOut, busy, error } = useAuth();
  return (
    <Screen
      title="Your account"
      subtitle="One account for enjoying meals and managing your kitchen."
    >
      <Card mode="outlined">
        <Card.Content style={{ gap: 16 }}>
          <Text variant="titleMedium">{user?.name || "Welcome"}</Text>
          {user?.phone && <Text variant="bodyMedium">{user.phone}</Text>}
          <Button mode="outlined" loading={busy} disabled={busy} onPress={() => void signOut()}>
            Sign out
          </Button>
          {error && (
            <HelperText type="error" visible>
              {error}
            </HelperText>
          )}
        </Card.Content>
      </Card>
    </Screen>
  );
}
