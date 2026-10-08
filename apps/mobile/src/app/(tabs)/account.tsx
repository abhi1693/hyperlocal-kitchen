import { useState } from "react";
import { Button, Card, HelperText, Text, TextInput } from "react-native-paper";
import { Screen } from "../../components/screen";
import { useAuth } from "../../auth/provider";
import { AuthError } from "../../auth/client";
import { useOnboarding } from "../../onboarding/provider";
import { validAddress } from "../../onboarding/state";
export default function AccountScreen() {
  const { user, signOut, busy, error } = useAuth();
  const { state, updateAddress, saving } = useOnboarding();
  const home = state?.membership;
  const [editing, setEditing] = useState(false);
  const [address, setAddress] = useState("");
  const [addressError, setAddressError] = useState<string | null>(null);
  const saveAddress = async () => {
    if (!validAddress(address) || saving) return;
    setAddressError(null);
    try {
      await updateAddress(address.trim() || null);
      setEditing(false);
    } catch (reason) {
      setAddressError(
        reason instanceof AuthError
          ? reason.message
          : "Could not save your address. Please try again.",
      );
    }
  };
  return (
    <Screen
      title="Your account"
      subtitle="One account for enjoying meals and managing your kitchen."
    >
      <Card mode="outlined">
        <Card.Content style={{ gap: 16 }}>
          <Text variant="titleMedium">{user?.name || "Welcome"}</Text>
          {user?.phone && <Text variant="bodyMedium">{user.phone}</Text>}
          <Button
            mode="outlined"
            loading={busy}
            disabled={busy || saving}
            onPress={() => void signOut()}
          >
            Sign out
          </Button>
          {error && (
            <HelperText type="error" visible>
              {error}
            </HelperText>
          )}
        </Card.Content>
      </Card>
      {home && (
        <Card mode="outlined">
          <Card.Content style={{ gap: 16 }}>
            <Text variant="titleMedium">Your community</Text>
            <Text variant="bodyLarge">{home.community_name}</Text>
            {home.zone_name && <Text variant="bodyMedium">{home.zone_name}</Text>}
            <Text variant="titleMedium">Home address</Text>
            {editing ? (
              <>
                <TextInput
                  mode="outlined"
                  label="Home address (optional)"
                  multiline
                  numberOfLines={3}
                  value={address}
                  disabled={saving}
                  onChangeText={(value) => {
                    setAddress(value);
                    setAddressError(null);
                  }}
                  error={!validAddress(address)}
                />
                <Text variant="bodySmall">
                  Include your flat, house or room number, street and landmark. Up to 250
                  characters.
                </Text>
                {!validAddress(address) && (
                  <HelperText type="error" visible>
                    Keep your address within 250 characters.
                  </HelperText>
                )}
                {addressError && (
                  <HelperText type="error" visible accessibilityLiveRegion="polite">
                    {addressError}
                  </HelperText>
                )}
                <Button
                  mode="contained"
                  loading={saving}
                  disabled={saving || !validAddress(address)}
                  onPress={() => void saveAddress()}
                >
                  Save address
                </Button>
                <Button disabled={saving} onPress={() => setEditing(false)}>
                  Cancel
                </Button>
              </>
            ) : (
              <>
                <Text variant="bodyMedium">
                  {home.address_label || "You haven’t added an address yet."}
                </Text>
                {home.status === "active" ? (
                  <Button
                    mode="outlined"
                    onPress={() => {
                      setAddress(home.address_label ?? "");
                      setAddressError(null);
                      setEditing(true);
                    }}
                  >
                    {home.address_label ? "Edit address" : "Add address"}
                  </Button>
                ) : (
                  <HelperText type="info" visible>
                    Your membership is suspended. Contact your community organiser.
                  </HelperText>
                )}
              </>
            )}
          </Card.Content>
        </Card>
      )}
    </Screen>
  );
}
