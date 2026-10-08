import { useEffect } from "react";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { Providers } from "../providers";
import { AuthProvider, useAuth } from "../auth/provider";
import { Splash } from "../components/splash";
import { OnboardingProvider, useOnboarding } from "../onboarding/provider";
import { OnboardingGate } from "../components/onboarding-gate";
import { ExperienceProvider, useExperience } from "../experience/provider";
import { ExperienceGate } from "../experience/gate";
void SplashScreen.preventAutoHideAsync().catch(() => undefined);
function Routes() {
  const { user, loading } = useAuth();
  const { state } = useOnboarding();
  const { state: experience } = useExperience();
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
  if (user && !state) return <OnboardingGate />;
  if (user && state?.completed && !experience) return <ExperienceGate />;
  return (
    <Stack initialRouteName="index" screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Protected guard={!user}>
        <Stack.Screen name="login" />
      </Stack.Protected>
      <Stack.Protected guard={!!user && state?.completed === false}>
        <Stack.Screen name="onboarding" />
      </Stack.Protected>
      <Stack.Protected guard={!!user && state?.completed === true && experience?.mode == null}>
        <Stack.Screen name="choose-experience" />
      </Stack.Protected>
      <Stack.Protected guard={!!user && state?.completed === true && experience?.mode != null}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
    </Stack>
  );
}
export default function RootLayout() {
  return (
    <Providers>
      <AuthProvider>
        <OnboardingProvider>
          <ExperienceProvider>
            <Routes />
          </ExperienceProvider>
        </OnboardingProvider>
      </AuthProvider>
    </Providers>
  );
}
