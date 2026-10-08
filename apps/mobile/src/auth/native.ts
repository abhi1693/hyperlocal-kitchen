import * as SecureStore from "expo-secure-store";
import { apiOrigin, AuthClient } from "./client";
export function createNativeAuthClient(): AuthClient {
  return new AuthClient(apiOrigin(process.env.EXPO_PUBLIC_API_URL, __DEV__), {
    fetch: (...args) => fetch(...args),
    get: SecureStore.getItemAsync,
    set: (key, value) =>
      SecureStore.setItemAsync(key, value, {
        keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
      }),
    remove: SecureStore.deleteItemAsync,
    now: Date.now,
  });
}
