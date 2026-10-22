# Changelog

## 0.1.1 — 2026-10-23

### Changes

- Move the Android/iOS application to Expo SDK 58 and React Native 0.88, preserving login, onboarding, and kitchen/customer entry routes.
- Keep onboarding scrolling compatible with React Native's component-ref types.
- Bound brace parser nesting in build and lint dependencies with the reviewed implementation and regression tests already used by DevFeed.

### Upgrade notes

- Rebuild native development clients after the SDK upgrade. Keep mobile React 19.3.0 and TypeScript 6.0.3 aligned with Expo's supported versions.
- Release preparation remains blocked by the upstream-unpatched node-forge signature verification advisory in Expo CLI/code-signing tooling. The required security gate remains enabled.
