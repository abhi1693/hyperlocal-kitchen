import { useEffect } from "react";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { Providers } from "../providers";
import { AuthProvider, useAuth } from "../auth/provider";
import { Splash } from "../components/splash";
void SplashScreen.preventAutoHideAsync().catch(() => undefined);
function Routes() {
  const { user, loading } = useAuth();
  useEffect(() => {
    if (!loading) void SplashScreen.hideAsync().catch(() => undefined);
  }, [loading]);
  if (loading)
    return (
      <Splash
        onLayout={() => {
          void SplashScreen.hideAsync().catch(() => undefined);
        }}
      />
    );
  return (
    <Stack initialRouteName="index" screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Protected guard={!user}>
        <Stack.Screen name="login" />
      </Stack.Protected>
      <Stack.Protected guard={!!user}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
    </Stack>
  );
}
export default function RootLayout() {
  return (
    <Providers>
      <AuthProvider>
        <Routes />
      </AuthProvider>
    </Providers>
  );
}
