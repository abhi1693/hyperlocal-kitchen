import { useEffect, useState, type PropsWithChildren } from "react";
import { AppState, useColorScheme } from "react-native";
import NetInfo from "@react-native-community/netinfo";
import {
  focusManager,
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { PaperProvider } from "react-native-paper";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { darkTheme, lightTheme } from "./theme";

export function Providers({ children }: PropsWithChildren) {
  const dark = useColorScheme() === "dark";
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, retry: 1 }, mutations: { retry: false } },
      }),
  );
  useEffect(() => {
    focusManager.setFocused(AppState.currentState === "active");
    const subscription = AppState.addEventListener("change", (state) =>
      focusManager.setFocused(state === "active"),
    );
    const unsubscribe = NetInfo.addEventListener((state) =>
      onlineManager.setOnline(state.isConnected === true && state.isInternetReachable !== false),
    );
    return () => {
      subscription.remove();
      unsubscribe();
    };
  }, []);
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={client}>
        <PaperProvider theme={dark ? darkTheme : lightTheme}>
          <StatusBar style={dark ? "light" : "dark"} />
          {children}
        </PaperProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
