# Hyperlocal Kitchen mobile

One Android/iOS app for residents and kitchen operators. The app opens with a name splash, then a custom phone login/register page. Local development currently skips OTP; production phone authentication is disabled until verification is implemented. After login, users without a community membership choose their community once, then choose whether to use the app for meals or their kitchen. An address is optional and can be edited from Account. Kitchen owners can set up their kitchen, dishes, pickup points, and dated menus. Resident ordering screens are still being built. Platform administration stays in the existing web app.

## Stack and decisions

- Expo SDK 57 (stable), React Native 0.86, React 19.2, strict TypeScript. Use `npx expo install` from this directory for SDK-compatible native dependency versions.
- Expo Router for file-based navigation and the `hyperlocal-kitchen` deep-link scheme already expected by the backend.
- React Native Paper 5 for accessible Material 3 components. Central light/dark themes use warm food-oriented colours. Paper offers a complete form/dialog/card toolkit without introducing a second styling compiler. Gluestack/NativeWind and Tamagui are alternatives when custom utility styling or universal web/native sharing becomes a requirement; this app does not currently need that complexity.
- TanStack Query for server state, with foreground and connectivity integration. Mutations are never automatically retried; checkout must use the backend idempotency contract when implemented.
- Expo SecureStore persists origin-bound opaque backend bearer sessions. Provider tokens and client secrets stay on the backend.
- Expo development builds and Continuous Native Generation. Commit app config/plugins, not generated Android/iOS projects.
- Keep local UI state in React until a concrete need for an additional state manager appears.

Research: [React Native framework recommendation](https://reactnative.dev/blog/2024/06/25/use-a-framework-to-build-react-native-apps), [Expo Router setup](https://docs.expo.dev/router/installation/), [Paper theming](https://oss.callstack.com/react-native-paper/docs/guides/theming), [native generation](https://docs.expo.dev/workflow/continuous-native-generation/).

## Run locally

Run these commands from the repository root:

```sh
npm ci
npm run mobile:android
# On macOS with Xcode:
npm run mobile:ios
# After installing a development build on your phone/emulator:
npm run mobile:start
```

The `mobile:*` commands also work from `apps/mobile`. In that directory, the shorter `npm run android`, `npm run ios`, and `npm run start` commands are equivalent. Extra CLI arguments are supported, for example `npm run mobile:android -- --device`.

Android requires Android Studio/SDK and a JDK supported by this Expo release. iOS compilation requires macOS/Xcode. `run:android` and `run:ios` generate and compile the respective native project. Set `EXPO_PUBLIC_API_URL` in `apps/mobile/.env` to the same phone-reachable API origin as `KITCHEN_USER_BASE_URL`. Restart Metro after changing environment values. See [Zitadel setup and auth flow](../../docs/mobile-auth.md) for exact redirect URIs and native-build requirements. Public Expo environment variables must never contain secrets.

For cloud builds, from `apps/mobile` run `npx eas-cli@latest build:configure` with the project owner's Expo account, then `npx eas-cli@latest build --platform all --profile development`. Commit the resulting project ID once linked. Development, internal preview, and production profiles are defined in `eas.json`. Cloud builds/signing and store submission have not been performed. Confirm ownership of `com.hyperlocalkitchen.app` before distributing; it is the initial application identifier, not an assertion of store registration.

## Community onboarding

The API's `GET /api/v1/me/onboarding` decides whether community selection is needed. Any existing membership completes onboarding, including one created by an admin or one without an address. Membership status and community availability still control marketplace access through the backend; they do not restart first-use onboarding.

New residents select an active community, optionally select an active zone, and optionally enter their flat, building, or delivery address. Community lists are paginated. Saving calls `POST /api/v1/me/onboarding`; the backend returns the existing membership if setup was already completed on another device. The app checks the server again if the save response is lost. Community and zone creation stay in the admin app. Account updates the address through the self-service membership endpoint; clearing it leaves onboarding complete.

Session restoration checks onboarding before opening protected tabs or deep links. A failed status request displays a retry action. State is scoped to the API origin and signed-in account.

## Meals and kitchen experiences

`GET /api/v1/me/experience` returns the account's saved `mode` and its owned kitchen. New accounts choose `customer` or `kitchen_owner` through `PATCH /api/v1/me/experience`; Account can change that preference later. Existing owners without a saved preference open their kitchen experience automatically. The choice is stored on the server and survives reinstallations. Choosing kitchen mode does not grant ownership or administrative permissions: each API request still checks the account's actual membership and kitchen relationships. An account can own one kitchen.

The Kitchen workspace creates and edits the kitchen profile, including fulfillment settings and optional address, UPI ID, and FSSAI number. An empty address does not block kitchen setup; an existing onboarding address is inherited on creation when no replacement is supplied. New kitchens await platform-admin approval. Owners can manage dishes and save draft menus while pending; publishing requires approval and a future order cutoff. Pickup points require an actual pickup address and remain separate from the optional profile address.

Menu forms use rupees and whole portions, then send exact integer paise and aware India timestamps to the API. Ready windows must end after they start and cover at most 24 hours; orders must close by the window's end. Pickup and delivery choices must be enabled on the kitchen. Backend validation remains authoritative for current eligibility, inventory reservations, cancellation, and ownership. Existing published or sold-out menus support stock corrections after cutoff; editing them does not automatically republish a draft.

## Generated API models

Run from the repository root after changing a backend schema:

```sh
npm run mobile:generate
```

This exports the backend OpenAPI contracts, generates mobile TypeScript schemas with the existing Orval dependency, and generates community type labels from the same backend enum used by the admin app. Import models from `src/api/generated` and labels from `src/api/community-type-choices`; do not copy admin API models or edit generated files. Mobile requests continue using the authenticated application client. Orval receives an empty paths map and writes only models and an empty metadata file inside the generated directory. Cleanup is disabled so generation cannot remove application or native source files.

From `apps/mobile`, `npm run generate` uses the already exported `docs/openapi/api.json`. CI regenerates those models and checks for changes; the backend/admin contract job also verifies OpenAPI and the shared community labels.

## Verification and maintenance

```sh
npm run mobile:lint
npm run mobile:typecheck
npm run mobile:export
npm run mobile:test
cd apps/mobile
npx expo-doctor
npx expo install --check
```

CI checks generated contracts, lint/types, runs mobile tests, and generates both Android and iOS production JavaScript bundles. Bundling does not prove a signed native build or device behaviour. Pre-commit checks mobile lint/types and tests. The root pins the mobile-compatible React/React DOM pair so shared mobile libraries resolve the correct React instance; the admin workspace keeps its own React 19.3 pair. Root overrides keep Reanimated and Worklets on Expo-compatible versions. Upgrade SDKs deliberately, run Expo Doctor, regenerate both native projects, and smoke-test navigation, light/dark themes, large text, sessions, and deep links on both platforms.

Verify the phone login/register/logout, community onboarding, experience choice, kitchen setup, and draft/publish loops on real devices, then implement resident ordering. Kitchen-owner capabilities must be authorized by the backend; community creation and kitchen approval remain platform-admin only.

## Dependency audit limitation

The SDK 57 and Jest dependency audit on 2026-10-08 reports 68 affected packages (53 high, 15 moderate), cascading from advisories in `braces`, `decode-uri-component`, `node-forge`, `sprintf-js`, and `uuid`. Several have no patched version published; other fixes require incompatible module changes or major transitive overrides. Automatic forced fixes propose obsolete Expo/React Native downgrades. The repository security gate remains enabled; a clean audit is not claimed. Revisit these advisories as upstream releases arrive and before distribution.
