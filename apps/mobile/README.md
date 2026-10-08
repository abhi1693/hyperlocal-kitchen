# Hyperlocal Kitchen mobile

One Android/iOS app for residents and kitchen operators. This initial scaffold has Discover, Orders, and Account tabs with honest empty states; authentication and marketplace API integration are the next task. Platform administration stays in the existing web app.

## Stack and decisions

- Expo SDK 57 (stable), React Native 0.86, React 19.2, strict TypeScript. Use `npx expo install` from this directory for SDK-compatible native dependency versions.
- Expo Router for file-based navigation and the `hyperlocal-kitchen` deep-link scheme already expected by the backend.
- React Native Paper 5 for accessible Material 3 components. Central light/dark themes use warm food-oriented colours. Paper offers a complete form/dialog/card toolkit without introducing a second styling compiler. Gluestack/NativeWind and Tamagui are alternatives when custom utility styling or universal web/native sharing becomes a requirement; this app does not currently need that complexity.
- TanStack Query for server state, with foreground and connectivity integration. Mutations are never automatically retried; checkout must use the backend idempotency contract when implemented.
- Expo SecureStore installed/configured for the upcoming opaque bearer session integration; there is no token storage or login UI yet.
- Expo development builds and Continuous Native Generation. Commit app config/plugins, not generated Android/iOS projects.
- Keep local UI state in React until a concrete need for an additional state manager appears.

Research: [React Native framework recommendation](https://reactnative.dev/blog/2024/06/25/use-a-framework-to-build-react-native-apps), [Expo Router setup](https://docs.expo.dev/router/installation/), [Paper theming](https://oss.callstack.com/react-native-paper/docs/guides/theming), [native generation](https://docs.expo.dev/workflow/continuous-native-generation/).

## Run locally

From the repository root:

```sh
npm ci
npm run mobile:android
# On macOS with Xcode:
npm run mobile:ios
# After installing a development build on your phone/emulator:
npm run mobile:start
```

Android requires Android Studio/SDK and a JDK supported by this Expo release. iOS compilation requires macOS/Xcode. `run:android` and `run:ios` generate and compile the respective native project. Physical devices need a reachable LAN API address when API integration is added; Android emulator uses `10.0.2.2` for the host. `.env.example` is a template for that future integration, not a live connection in this scaffold. Public Expo environment variables must never contain secrets.

For cloud builds, from `apps/mobile` run `npx eas-cli@latest build:configure` with the project owner's Expo account, then `npx eas-cli@latest build --platform all --profile development`. Commit the resulting project ID once linked. Development, internal preview, and production profiles are defined in `eas.json`. Cloud builds/signing and store submission have not been performed. Confirm ownership of `com.hyperlocalkitchen.app` before distributing; it is the initial application identifier, not an assertion of store registration.

## Verification and maintenance

```sh
npm run mobile:lint
npm run mobile:typecheck
npm run mobile:export
cd apps/mobile
npx expo-doctor
npx expo install --check
```

CI checks lint/types and generates both Android and iOS production JavaScript bundles. Bundling does not prove a signed native build or device behaviour. Pre-commit checks mobile lint/types. The root pins the mobile-compatible React/React DOM pair so shared mobile libraries resolve the correct React instance; the admin workspace keeps its own React 19.3 pair. Root overrides keep Reanimated and Worklets on Expo-compatible versions. Upgrade SDKs deliberately, run Expo Doctor, regenerate both native projects, and smoke-test navigation, light/dark themes, large text, sessions, and deep links on both platforms.

Before adding real screens, implement and verify the existing PKCE authentication handoff end to end, then community selection and resident ordering. Add API types from the mobile backend OpenAPI rather than copying admin contracts. Kitchen-owner capabilities must be authorized by the backend; community creation remains platform-admin only.

## Dependency audit limitation

The initial SDK 57 dependency audit reports upstream advisories in the Expo/Metro toolchain, including `braces` and `node-forge` with no fixed version currently published in the registry. Automatic forced fixes propose obsolete Expo/React Native downgrades. The repository security gate remains enabled; a clean audit is not claimed. Revisit these advisories as upstream releases arrive and before distribution.
