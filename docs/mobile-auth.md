# Mobile phone sign-in

The Android and iOS app opens a name-only splash and then its own phone
login/registration screen. For development, entering a phone creates or restores
a local Kitchen profile and an opaque application session. OTP verification is
deferred. No SMS is sent, no phone ownership is verified, and no ZITADEL account
is created by this flow. Residents and kitchen operators share the mobile app;
platform admins continue using the separate ZITADEL admin application.
No ZITADEL console changes are needed to use the development phone flow.

## Enable the development flow

Set these values in the ignored root `.env`:

```dotenv
KITCHEN_ENVIRONMENT=development
KITCHEN_DEVELOPMENT_PHONE_LOGIN=true
KITCHEN_USER_BASE_URL=http://<development-computer-LAN-IP>:18000
KITCHEN_COOKIE_SECURE=false
```

Set the reachable API origin in the ignored `apps/mobile/.env`:

```dotenv
EXPO_PUBLIC_API_URL=http://<development-computer-LAN-IP>:18000
```

Restart the API after changing its environment and restart Expo after changing
`EXPO_PUBLIC_API_URL`. Start the installed development app from the repository
root with `npm run mobile:android`, or `npm run mobile:ios` on macOS with Xcode.
Use the same network for a physical phone and the development computer.
`localhost` on a phone refers to the phone; an Android emulator reaches its host
through `10.0.2.2`.

The app checks `GET /api/v1/auth/config` for `phone_login_enabled`. To create or
restore a development session, it calls:

```http
POST /api/v1/auth/mobile/phone
Content-Type: application/json
```

```json
{"phone": "+919876543210"}
```

The API accepts an E.164-style number matching `^\+[1-9][0-9]{7,14}$` and returns
`session_token`, `expires_at`, and the application `user`. The app stores the
session in SecureStore and sends `Authorization: Bearer <session_token>`.
`GET /api/v1/auth/me` restores and renews the session; logout revokes it and
deactivates its notification devices.

The backend enables this endpoint only when both
`KITCHEN_ENVIRONMENT=development` and `KITCHEN_DEVELOPMENT_PHONE_LOGIN=true`.
Otherwise it returns `503 auth_not_configured` without creating a profile. The
development flag cannot enable the flow in production.

## Development identities and production gate

These profiles use the separate issuer `urn:kitchen:development:phone`.
They do not represent verified ZITADEL identities. Anyone able to reach the
enabled endpoint can enter a phone number and obtain its development profile;
use this mode only for local development data. It must not provide access to real
customer accounts or orders. A kitchen relationship is still authorized by the
API, and this route grants no platform-admin role.

Production phone login requires actual proof of phone ownership, such as SMS
OTP, and a completed identity/account creation design before this bypass can be
replaced. Development profiles must not be silently linked to production
accounts merely because a number matches.

The intended production direction is a custom phone-only login backed by
ZITADEL. Its current User v2 API still requires email and profile fields, so
phone-only registration needs an explicit supported account-provisioning
decision. A new Native client alone does not remove that requirement. We have
not created placeholder emails or passwords. See
[the current user creation contract](https://github.com/zitadel/zitadel/blob/main/proto/zitadel/user/v2/user_service.proto)
and [the open optional-fields issue](https://github.com/zitadel/zitadel/issues/4386).

ZITADEL's Session API can challenge and verify SMS for an existing user with a
verified phone and SMS enrollment, but that does not solve creating a new
phone-only user. No SMS provider is required for the current development flow.
The [official SMS session guide](https://zitadel.com/docs/guides/integrate/login-ui/mfa)
describes the prerequisite enrollment and checks.

## Optional Native client setup for future ZITADEL integration

The supplied Native client ID is retained in the ignored local `.env` as
`KITCHEN_USER_OIDC_CLIENT_ID`. The following optional settings prepare the
backend-supported browser/OIDC contract for a future client integration. The
current native client implements phone login only; it does not launch a browser
or implement the PKCE handoff. These settings do not turn a development phone
profile into a ZITADEL account.

1. Open the Kitchen project in the intended organization. Create a **Native**
   application dedicated to the mobile experience. Keep the admin client separate.
2. Use Authorization Code with PKCE S256, response type `code`, and token endpoint
   authentication `none`. The Native client ID is public; no client secret belongs
   in the mobile app. The API performs the provider exchange.
3. In **Redirect Settings**, register the Kitchen API callback for the environment
   you are using. The callback must exactly match `KITCHEN_USER_BASE_URL` followed
   by `/api/v1/auth/callback`:

   | Environment | ZITADEL redirect URI |
   | --- | --- |
   | Local browser on the development computer | `http://localhost:18000/api/v1/auth/callback` |
   | Phone on the same network | `http://<development-computer-LAN-IP>:18000/api/v1/auth/callback` |
   | Production | `https://<public-Kitchen-API-host>/api/v1/auth/callback` |

4. Enable **Development Mode** on the development client for HTTP LAN callbacks.
   Native HTTP callbacks outside localhost/loopback are noncompliant when strict
   validation is enabled. Production uses an HTTPS API callback with Development
   Mode disabled. Prefer a separate production client and exact callback entries.
   [ZITADEL's application guide](https://zitadel.com/docs/guides/manage/console/applications-overview)
   describes development settings; its
   [redirect validation source](https://github.com/zitadel/zitadel/blob/main/internal/domain/application_oidc.go)
   confirms that HTTPS callbacks are valid for Native code-flow applications.
5. If using Login V2, enable **Use new login UI** for this application when the
   instance has not already enabled it. Leave its custom base URL empty when using
   the instance's hosted UI. See
   [hosted Login V2 configuration](https://zitadel.com/docs/guides/integrate/login/hosted-login).
6. Select the target organization's login behavior to match the eventual
   production authentication design. Hosted local registration currently asks
   for email and profile information, and hosted SMS is a second factor. Enabling
   those settings does not provide the requested phone-only registration. See
   [onboarding settings](https://zitadel.com/docs/guides/integrate/onboarding/end-users)
   and [hosted login](https://zitadel.com/docs/guides/integrate/login/hosted-login).

The mobile deep link `hyperlocal-kitchen://auth/callback` is a separate redirect
sent by the Kitchen API after it has validated ZITADEL's callback. For this
architecture, registering that deep link alone in ZITADEL is insufficient: the
provider redirects to the API, and the API then redirects to the installed app.

## Future OIDC backend settings

The existing provider flow uses your issuer, organization and mobile client ID
in the ignored root `.env`. For a phone connected to the development computer's
network:

```dotenv
KITCHEN_ENVIRONMENT=development
KITCHEN_OIDC_ISSUER_URL=https://<ZITADEL-host>
KITCHEN_OIDC_ORGANIZATION_ID=<organization-id>
KITCHEN_USER_OIDC_CLIENT_ID=<mobile-client-id>
KITCHEN_OIDC_TOKEN_ENDPOINT_AUTH_METHOD=none
KITCHEN_USER_BASE_URL=http://<development-computer-LAN-IP>:18000
KITCHEN_COOKIE_SECURE=false
```

The resident and admin APIs currently share the token endpoint authentication
method setting. Keep their client configurations consistent. Development HTTP
origins also require the existing admin origin to use HTTP because cookie
security is a shared backend setting.

For the OIDC browser flow, the phone must reach the API callback as well as the
app's API requests.
`localhost` on a phone refers to the phone. An Android emulator can reach its host
through `10.0.2.2`; if using that address as the public API origin, set
`KITCHEN_USER_BASE_URL` to the same origin and register its exact callback in
ZITADEL. A LAN address works for both a physical phone and the development
computer. Restart the API after changing its environment and restart Expo after
changing `EXPO_PUBLIC_API_URL`.

Production sets `KITCHEN_ENVIRONMENT=production`, HTTPS user/admin origins and
`KITCHEN_COOKIE_SECURE=true`. The mobile app's API origin and the API's callback
origin must be reachable by users' devices. The ZITADEL issuer remains HTTPS.

## Backend-supported OIDC handoff contract

The backend already exposes these endpoints, but the current native client does
not implement this flow. A future browser-based integration would:

1. Generate a random verifier and its SHA-256 PKCE challenge, then call
   `POST /api/v1/auth/mobile/start`. Set `register: true` for registration and open
   the returned URL in the system browser.
2. Complete the API's provider Authorization Code/PKCE flow with nonce and
   browser-bound state through ZITADEL.
3. Receive `hyperlocal-kitchen://auth/callback?code=...` after ZITADEL returns to
   the registered API callback and the API validates the token, subject and
   organization. The backend handoff code is single-use and expires in 60 seconds.
4. Exchange the handoff code and the original verifier through
   `POST /api/v1/auth/mobile/exchange`.
5. Store the returned opaque Kitchen session in SecureStore and send
   `Authorization: Bearer <session_token>`. Provider tokens would stay on the
   server.
6. Restore and renew the session through `GET /api/v1/auth/me`, and revoke it
   through logout, which also deactivates its notification devices.

The native handoff PKCE protects the API-to-app exchange; the provider PKCE
protects the separate ZITADEL-to-API exchange. A client ID or callback parameter
is not an authenticated Kitchen session.

## Future SMS provider setup

If later using ZITADEL's SMS service, configure an active SMS provider under
**Default Settings → Notification Settings → SMS**. ZITADEL supports Twilio
credentials with a sender number or a Verify Service SID. Enable **OTP SMS** in
the organization's second factors. Users must add and verify their phone and
enroll the method; test that flow on the selected hosted-login version. Provider
credentials stay in ZITADEL. See
[SMS provider and MFA settings](https://zitadel.com/docs/guides/manage/console/default-settings)
and [SMS enrollment and checks](https://zitadel.com/docs/guides/integrate/login-ui/mfa).

These hosted-login settings add a second factor to the selected primary method.
A custom phone-only login requires its own verified authentication flow and the
account-provisioning decision described above. No provider setup or live SMS
delivery has been performed for the current development phone screen.

## Device verification

Use installed development builds on Android and iOS. Confirm splash → phone
entry → app, invalid numbers, relaunch/session restoration, logout, disabled
development login, and API error handling. Production phone verification and
the future ZITADEL handoff need separate live tests once implemented. Unit tests
and JavaScript exports do not replace a device check or prove SMS delivery.
