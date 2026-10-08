import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, View, ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Button, HelperText, Text, TextInput, useTheme } from "react-native-paper";
import { useAuth } from "../auth/provider";
import { PHONE } from "../auth/client";
export default function LoginScreen() {
  const theme = useTheme();
  const { signInWithPhone, retry, busy, error } = useAuth();
  const [phone, setPhone] = useState("+91 ");
  const [validation, setValidation] = useState<string | null>(null);
  const [attemptedSignIn, setAttemptedSignIn] = useState(false);
  const submit = () => {
    const normalized = phone.replace(/[\s()-]/g, "");
    if (!PHONE.test(normalized)) {
      setValidation("Enter your phone number with its country code.");
      return;
    }
    setValidation(null);
    setAttemptedSignIn(true);
    void signInWithPhone(normalized);
  };
  return (
    <SafeAreaView style={[styles.page, { backgroundColor: theme.colors.background }]}>
      <KeyboardAvoidingView
        style={styles.page}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}>
          <View style={styles.content}>
            <Text variant="labelLarge" style={{ color: theme.colors.primary }}>
              HYPERLOCAL KITCHEN
            </Text>
            <Text variant="displaySmall" accessibilityRole="header">
              Welcome to your neighbourhood table
            </Text>
            <Text variant="bodyLarge" style={{ color: theme.colors.onSurfaceVariant }}>
              Sign in or create an account with your phone number.
            </Text>
            <View style={styles.actions}>
              <TextInput
                mode="outlined"
                label="Phone number"
                value={phone}
                onChangeText={(value) => {
                  setPhone(value);
                  setValidation(null);
                }}
                keyboardType="phone-pad"
                textContentType="telephoneNumber"
                autoComplete="tel"
                autoCapitalize="none"
                maxLength={24}
                disabled={busy}
                error={!!validation}
                onSubmitEditing={() => {
                  if (!busy) submit();
                }}
                accessibilityLabel="Phone number including country code"
              />
              <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant }}>
                Include your country code, for example +91 98765 43210.
              </Text>
              {validation && (
                <HelperText type="error" visible>
                  {validation}
                </HelperText>
              )}
              <Button
                mode="contained"
                contentStyle={styles.button}
                disabled={busy}
                loading={busy}
                onPress={submit}
              >
                Continue
              </Button>
            </View>
            <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant }}>
              New here? We’ll create your account when you continue.
            </Text>
            {error && (
              <View accessibilityLiveRegion="polite">
                <HelperText type="error" visible>
                  {error}
                </HelperText>
                <Button disabled={busy} onPress={() => (attemptedSignIn ? submit() : void retry())}>
                  Try again
                </Button>
              </View>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
const styles = StyleSheet.create({
  page: { flex: 1 },
  scroll: { flexGrow: 1, justifyContent: "center", padding: 28 },
  content: { width: "100%", maxWidth: 480, alignSelf: "center", gap: 24 },
  actions: { gap: 14, marginTop: 12 },
  button: { minHeight: 52 },
});
