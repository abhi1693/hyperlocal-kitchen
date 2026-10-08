# Hyperlocal Kitchen

FastAPI backend for a private hyperlocal food marketplace for communities.
Each user can own at most one kitchen across all communities, including pending and
suspended kitchens. Managers can help operate other kitchens. Ownership creation and
assignment are protected by a database constraint. Before applying migration
`0008_single_kitchen_owner`, resolve any users with multiple owner memberships; the
migration rejects duplicates without changing ownership automatically.

Members and kitchen owners share one account and one mobile API. Platform administration has
a separate API and Zitadel application. The admin web app lives in `apps/admin`; the mobile app scaffold lives in `apps/mobile`.

## MVP

- Platform admins manage users, communities, zones, memberships, kitchens, dishes,
  dated listings and orders across communities. They approve kitchens and manage
  who can operate a kitchen.
- Members select a community and optionally provide a home zone and address label.
  Joining activates membership immediately, with no invitation or membership approval.
- One account can join multiple communities, such as home, office and other locations.
  Each membership keeps its own zone, address and status.
- Kitchen owners create reusable dishes and publish dated listings with price,
  portions, cutoff and pickup/delivery windows. Future listings supply the weekly
  menu; cooking again reuses the same dish.
- Members discover food only within an active community membership and place
  orders from one kitchen and one service window at a time.
- Kitchens accept/reject orders, then mark preparing, ready and completed.
  Customers can cancel before preparation. Unaccepted orders expire after
  15 minutes or at the cutoff, whichever comes first.
- PostgreSQL reserves portions atomically. Rejection, cancellation and expiry
  release them once. An `Idempotency-Key` makes checkout retries safe.
- Payment goes directly to the kitchen. Customers can report payment and kitchen
  owners can confirm it; there is no payment processor or commission.
- Orders produce an in-app inbox. An optional Expo push adapter is disabled by
  default. Registered devices are bound to their signed-in session.

Community types are `residential_society`, `cantonment`, `housing_colony`,
`university`, `corporate_campus`, `gated_community` and `other`. Zones can form a
hierarchy and use `tower`, `area`, `hostel`, `block` or `other` as their type.
Communities can activate without zones; home zones and addresses are optional.

Communities have no timezone or access-instructions fields. Menu dates use India
time internally. Dishes contain only their name, optional description and photo
URL, kitchen relationship and active flag. Orders link to the customer user;
their name is read from that user. Item names/prices and the selected fulfillment
destination are snapshotted so existing orders keep their agreed details. Kitchen names are
also read from the linked kitchen. The order timeline is the single source for
status timestamps and rejection reasons. Delivery fees belong to the kitchen;
listings show that fee and orders snapshot it at checkout.

No audit logs, payments infrastructure, delivery fleet,
chat, subscriptions, ratings or analytics are included. Photo URLs can be
provided; uploading photos to object storage is not implemented yet.

## Structure

```text
apps/api/src/          Member and kitchen-owner FastAPI application
apps/admin-api/src/    Platform-admin FastAPI application
apps/admin/            Next.js admin UI with atomic components and generated React Query hooks
apps/worker/src/       Pending-order expiry and optional push dispatch
packages/core/src/    Models, contracts, business logic and Zitadel sessions
packages/http/src/    Shared HTTP errors, auth and application setup
migrations/           Alembic schema migrations
tests/                PostgreSQL and Redis integration tests
docs/openapi/         Generated contracts for both applications
```

The Python 3.12+ uv workspace follows DevFeed's service/shared-package layout.

## Model relationships

| Connection | Cardinality | Model/link |
| --- | --- | --- |
| User ↔ Community | Many-to-many | Membership, with optional zone, address label and membership status |
| User ↔ Kitchen | Many-to-many | KitchenMember, with owner/manager role |
| Community → CommunityZone / Kitchen / PickupPoint | One-to-many | Community foreign keys |
| CommunityZone → CommunityZone | One-to-many | Optional parent in the same community |
| MenuListing ↔ PickupPoint | Many-to-many | ListingPickupPoint, constrained to the kitchen community |
| Kitchen → Dish → MenuListing | One-to-many at each step | Reusable dish, dated availability |
| User / Kitchen → Order | One-to-many | Customer and kitchen foreign keys |
| Order ↔ MenuListing | Many-to-many | OrderItem, with quantity and agreed name/price |
| Order → OrderEvent / Notification | One-to-many | Timeline and resident alerts |
| Order → OrderIdempotency | One-to-one, optional | Checkout retry key |
| User → Device | One-to-many | Push device, bound to its Redis session |

The existing user, kitchen and commerce ORM relationships are bidirectional
with `back_populates`; pickup-point links use explicit foreign keys. Association objects
are the writable path; direct user/community/kitchen collections are read-only.
UUID primary keys and unique association keys prevent duplicate links.
Composite foreign keys enforce that zones belong to the selected community,
dishes belong to their listing's kitchen, orders belong to their kitchen's
community, and retry keys belong to the order's customer. Historical records
restrict hard deletion; the API uses suspension, cancellation and archiving.
These fixed entities use typed foreign keys, with no generic relation required.
The association-object pattern follows the [SQLAlchemy relationship documentation](https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#association-object).

## Run locally

```sh
# For a fresh checkout, first copy .env.example to .env and configure Zitadel.
docker compose up --build --watch
```

Docker Compose starts PostgreSQL, Redis, migrations, both APIs, the admin UI and the worker.
The project's local `.env` is configured for admin development. It selects
`compose.yaml` and `compose.build.yaml` through `COMPOSE_FILE`. Member API docs:
`http://localhost:18000/docs`. Platform-admin API docs:
`http://localhost:13001/docs`. `/health` reports process health; `/ready` checks
the database migration. Blank Zitadel settings leave authentication disabled;
protected endpoints remain unavailable until configuration is supplied. Resident
authentication can be configured later while the admin foundation is developed.

Watch rebuilds the API, admin API and worker when Python source or dependencies
change, matching DevFeed's native watch workflow. Separate local image tags keep
service rebuilds isolated. PostgreSQL and Redis retain data in named volumes;
Redis enables AOF so recreating its container retains sign-in sessions.

Application ports bind to `KITCHEN_BIND_IP` (default `0.0.0.0`). PostgreSQL and
Redis stay on loopback ports `15432` and `16379`, avoiding the host PostgreSQL on
`5432`. Change the four port settings in `.env` as needed. For a phone or another
LAN device, set the API base URLs to this computer's reachable address and
register matching Zitadel callback URLs; `0.0.0.0` is a bind address, not an origin.

To keep the stack running when stopping the watcher:

```sh
docker compose up -d --build --wait
docker compose watch --no-up
```

Native watch handles source/dependency rebuilds. After adding migrations or
changing `.env`/Compose settings, stop the watcher and apply the changes with:

```sh
docker compose build
docker compose up -d --wait postgres redis
docker compose stop api admin-api worker
docker compose up --no-deps --force-recreate --exit-code-from migrate migrate
docker compose up --no-deps --force-recreate --watch api admin-api worker
```

Start the application services after the migration succeeds. This preserves the
database and Redis volumes. A restart alone does not reload
Compose environment values. See [Docker's Compose Watch documentation](https://docs.docker.com/compose/how-tos/file-watch/).

For development without API containers:

```sh
uv sync --all-packages
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn kitchen_api.main:app --reload --port 18000 --no-access-log
```

Run `uv run uvicorn kitchen_admin_api.main:app --reload --port 13001 --no-access-log` and
`uv run kitchen-worker` in separate terminals. The local database URLs in
`.env.example` use the published loopback ports; Compose overrides them with
container service names. Use HTTPS origins and secure cookies for production;
the provided Compose file is a local development configuration.

## Zitadel configuration

Authentication follows DevFeed's implementation: authorization code with PKCE,
nonce and browser-bound single-use state, validated ID token and matching
userinfo subject, and opaque Redis sessions. Provider tokens stay on the server.
Zitadel identifies accounts; verified phone numbers are delivery contacts and can
be shared by separate accounts.

For admin development, set the issuer, organization ID, admin client ID and admin
base origin in `.env`. The local file already contains the supplied admin
organization and client IDs. Resident authentication can stay blank until work
on the mobile app starts; it will use a separate OIDC application.

In the admin application's Zitadel Redirect Settings, register
`http://localhost:3001/api/v1/auth/callback` and enable Development Mode for
local HTTP. See [Zitadel's application settings](https://zitadel.com/docs/guides/manage/console/applications-overview#redirect-uris).

The backend redirect URIs for the two applications are:

```text
http://localhost:18000/api/v1/auth/callback
http://localhost:3001/api/v1/auth/callback
```

Configure authorization code with PKCE S256. Public PKCE clients use token
endpoint authentication `none`. Confidential clients require their respective
client secrets and the configured `client_secret_basic` or `client_secret_post`
method. Both applications currently use the same token endpoint auth method.

Create the project role `platform_admin` (or change
`KITCHEN_ADMIN_REQUIRED_ROLE`) and grant it only to platform admins in the
configured organization. Admin login requests and checks that exact role under
that organization's Zitadel role assertion. A kitchen-owner relationship grants
no platform-admin access. See the official [Zitadel scopes documentation](https://zitadel.com/docs/apis/openidoauth/scopes).

Web clients use `GET /auth/login`, `GET /auth/me` and `POST /auth/logout` under
their API prefix. Cookies are HttpOnly and SameSite Lax. Mutations authenticated
by cookie require the matching `Origin` and `X-CSRF-Token` returned by `/auth/me`.
The admin UI proxies its API under the configured origin; provider callbacks and cookies stay on that origin.

Mobile login adds a small handoff to the same server-managed Zitadel flow:

1. Generate a PKCE verifier and SHA-256 challenge in the app.
2. `POST /api/v1/auth/mobile/start` with `code_challenge`; open the returned
   `authorization_url` in the system browser.
3. Handle `hyperlocal-kitchen://auth/callback?code=...`. This code lasts 60 seconds.
4. `POST /api/v1/auth/mobile/exchange` with `code` and `code_verifier`.
5. Store `session_token` in platform secure storage and send it as
   `Authorization: Bearer <session_token>`.

This bearer value is an opaque app session, not a Zitadel access token. Native
and browser sessions are separate. Native sign-in preserves any existing browser
session. Logout revokes the session and deactivates its devices. `/auth/me` renews
resident sessions within a 90-day absolute limit.
Admin sessions last eight hours. Redis session data must persist across restarts
if retaining signed-in users matters. No local passwords, OTP service or admin
API keys are implemented. A real provider login still needs your client settings.

## Essential API flows

| Client | Prefix | Main resources/actions |
| --- | --- | --- |
| Platform admin | `/api/v1` on the admin API | Users, communities, zones, memberships, kitchens and members, dishes, listings, orders |
| Member | `/api/v1` | Community/zone selection, joining, today's menu, kitchens, orders, profile |
| Kitchen owner | `/api/v1` | Dishes, menu listings, own kitchen orders and status actions |

Admin-created communities start as drafts and can activate with no zones.
Onboarding is `POST /api/v1/communities/{id}/join` with optional `zone_id` and
`address_label`; an empty object is valid. A supplied zone must be active and
belong to the selected community. Joining returns an active membership immediately.
Explicitly suspended memberships can only be
restored by an admin through `/api/v1/memberships/{id}/activate`.
Kitchen setup accepts an independent `zone_id` and `address_label`. Omitted location
fields initially use the owner's membership address; explicit nulls clear that
default. Subsequent home-address edits do not move the kitchen. Kitchen approval
requires a 14-digit FSSAI registration/license number; this stores the supplied
number and does not verify it against a registry.

The admin API follows DevFeed's resource-router pattern. Lists support `q`,
`sort`, `limit` and `offset`, returning `{items, total, limit, offset}`. Sort fields
are allowlisted and pagination is bounded. Typed request/response schemas supply
the contract for the admin web app; exports live in `docs/openapi`.

Admin routes use the same organization-scoped Zitadel role and CSRF checks.
Editable fields use `PATCH`; lifecycle changes use explicit actions such as
approval, suspension, archiving and order preparation. Admins can place an order
for an existing resident and perform the normal order/payment actions. These
actions share customer/kitchen validation, inventory reservation and release,
order snapshots and notifications. Totals and reserved portions remain derived.
Orders retain their history, and deleting referenced records returns a conflict.
Zitadel owns account identities; admin user editing changes the application
profile and account activation, without manufacturing local login identities.
Deactivation suspends the user's memberships and disables their push devices;
kitchens are suspended when they lose their last active resident owner.

Use `GET /api/v1/communities/{id}/menu?date=2026-10-06` for a daily menu, or
`?from=2026-10-06&to=2026-10-12` for a week. Kitchen-specific menus use the same
date filters. All money is integer paise; timestamps include a UTC offset.

Checkout accepts listing IDs, quantities, `fulfillment_type` (`pickup` or
`delivery`), destination details and an optional note.
The server derives the customer, kitchen, community, price, fees and total. Supply
an `Idempotency-Key` header, reusing it only for a retry of the same order.
An order is pending until accepted; customer cancellation is allowed from
pending or accepted, and only the owning kitchen can advance preparation.

## Pause and resume orders

Kitchen operators can immediately pause new orders with
`POST /api/v1/kitchens/{id}/pause`, optionally sending
`{"reason": "Not cooking today"}`. The body may be omitted; reasons are trimmed,
limited to 500 characters, and empty reasons become null. Use
`POST /api/v1/kitchens/{id}/resume` with no body to accept orders again.
Both return the updated kitchen and use the same access rules as kitchen edits:
the operator needs an active community membership, the community must be active,
and a suspended kitchen cannot be changed.

New and existing kitchens default to `is_accepting_orders: true`. Pausing sets
this to false and records `paused_at`; repeated pauses preserve that timestamp
and replace the reason. Resuming clears the timestamp and reason. A pause lasts
until resumed and applies to all new orders, including future dated menus.
It does not change the kitchen's approval status or listing status.

Discovery still shows paused kitchens and their menus, exposing
`is_accepting_orders` and `pause_reason`; owner responses also include `paused_at`.
Listings from a paused kitchen have `is_orderable: false`. New checkout returns
HTTP 409 with code `kitchen_not_accepting_orders`, including admin-created orders.
Existing orders, stock reservations, payments and fulfillment continue normally;
retrying the same committed order with its idempotency key still returns that order.
Concurrent pause and checkout serialize: a checkout already reserving may commit
before pause returns; subsequent checkout sees the pause.

Apply migration `0006_kitchen_availability` before running the updated services.
There are no dated schedules or recurring hours in this control.

## Follow kitchens

`POST /api/v1/kitchens/{id}/follow` follows an approved kitchen visible in one of
the account's active communities. Paused kitchens can still be followed. The body
is optional; `{"notify_new_menu": true}` opts in to future menu notifications,
and false opts out. Menu delivery is designed but not implemented yet; see
[menu notifications](docs/menu-notifications.md).

The response contains `kitchen`, `followed_at` and `notify_new_menu`. Following is
safe to repeat: it preserves the original timestamp and, when the preference is
omitted, the current preference. New follows default to alerts off.
`DELETE /api/v1/kitchens/{id}/follow` returns 204 even if already unfollowed, and
allows cleanup after membership loss or kitchen suspension.

`GET /api/v1/me/followed-kitchens?limit=30&offset=0` returns a paginated list across
the account's active communities, newest follows first. Suspended kitchens and
inactive communities/memberships are hidden without deleting follows; paused
kitchens remain visible. Apply migration `0007_kitchen_follows` before using the
updated APIs.

## Preparation summary

Kitchen operators use `GET /api/v1/kitchens/{id}/prep-summary?date=2026-10-08` to
see outstanding preparation across pickup and delivery. The response contains
`kitchen_id`, `service_date`, `items`, `total_portions` and distinct `order_count`.
Each item has `dish_id`, the checkout snapshot's `dish_name`, `portion_count`,
distinct `order_count`, and `notes` linking customer notes to order IDs/numbers
and the relevant quantity. The same order's portions for a dish are combined.
Renamed dish snapshots remain separate rows so historical names are preserved.

Only accepted, preparing and ready orders whose ready window starts on the
requested Asia/Kolkata date count. Pending, completed, rejected, cancelled and
expired orders are excluded. An empty day returns an empty list and zero totals.
The summary reads order items on demand and stores no aggregate. Existing kitchen
order responses continue to include the full `customer_note`.

## Pickup and home delivery

A pickup point is a named collection location with an address label, optional
zone and instructions. It can be the home kitchen address or another place.
Platform admins create shared points through
`POST /api/v1/communities/{id}/pickup-points`. Kitchen owners manage their own
points through `GET/POST /api/v1/kitchens/{id}/pickup-points` and
`PATCH /api/v1/kitchens/{id}/pickup-points/{point_id}`. Members can list eligible
community points; owners cannot edit shared points or another kitchen's points.
Use `PATCH` with `active: false` to retire a point; referenced locations are retained.

A kitchen created with an address gets a pickup point at that address. These are
independent records: edit the pickup point when collection instructions or its
location change. Listings accept `pickup_point_ids`; omitting them on creation
defaults pickup to the kitchen's first eligible point. Pickup-enabled listings need
at least one point, and delivery-only listings have none. Listing responses
include eligible `pickup_points`. A point is eligible only when it is active and
has either no zone or an active zone in the same community. This rule applies to
member discovery, listing assignment, and automatic selection at listing creation
and checkout. Deactivating a zone hides its points from member discovery and
listing responses; pickup-only listings with no eligible points are not orderable.
Admin and kitchen management lists retain these points for editing, and existing
order snapshots and checkout retries remain unchanged. Offered points must belong
to the same community, and assignments cannot change while portions remain reserved.

For pickup checkout, send `pickup_point_id`. It must be eligible and offered by
every listing in the basket. If exactly one eligible point is common to all items,
omitting the ID selects that point. Multiple choices require an explicit ID.
No home address is required, and pickup has no delivery fee.

For delivery checkout, send `fulfillment_type: "delivery"` and optionally
`delivery_address: {"zone_id": "...", "address_label": "House 42"}`. Without an
explicit address, checkout uses the saved home address. A nonempty address label
is required; any zone must belong to the order's community and be active.
`PATCH /api/v1/me/memberships/{id}` lets members edit or clear their own home
location. Choosing delivery confirms the supplied or saved home address.
Delivery requires both kitchen and listing support and snapshots the kitchen fee.

New orders store a version 2 `fulfillment_snapshot` and only the relevant
`pickup_address` or `delivery_address`; the unused address is null. Pickup orders
also store `pickup_point_id`. The snapshot remains unchanged after location edits.
Idempotency hashes include submitted destination fields, so changing them with
the same key returns a conflict. Retrying a committed order still returns its
original destination even if the point has since been deactivated.

`GET /api/v1/kitchens/{id}/fulfillment-groups?service_date=YYYY-MM-DD` is available
to kitchen operators and platform admins. It groups accepted, preparing and ready
orders by service window and agreed destination, with separate order and portion
counts and linked order IDs. Pending, completed, rejected, cancelled and expired
orders are excluded. Each customer's payment and order lifecycle remain separate.
Dates use India time; destinations with different historical snapshots stay distinct.

## Multiple communities per account

A user can belong to one or more communities at the same time, for example a
residential community at home, a corporate campus at work, and another community.
There is one membership per user/community pair, with independent optional zone,
address label and status. Joining another community does not replace an existing
membership or move its saved address.

`GET /api/v1/me/communities` returns the account's memberships. Clients use the
selected community for menu discovery and fulfillment choices. Checkout derives
the community from the chosen kitchen and uses that community's membership for
a saved delivery address; it does not use a home address from another community.
Suspending membership in one community does not suspend the others.

## Client onboarding

The admin UI is implemented in `apps/admin`; the mobile navigation scaffold lives in `apps/mobile`. Their contracts
now support `Find your community → Join immediately → Browse menu`. Home details
are optional and can be collected at delivery checkout. Residential communities
can label zone/address inputs "Tower" and "Flat"; cantonments and other communities
can use "Area / Zone" and "Home address". Community type chooses labels, without
arbitrary dynamic forms. The proposed home-screen copy is
"What's cooking near you today?", alongside the selected community name.

## Community migration

`0005_communities_pickup` renames societies, towers and their foreign keys while
preserving existing UUIDs, membership states, kitchens, orders and reserved stock.
Existing societies become residential communities, towers become root tower zones,
and kitchen addresses become pickup points offered by existing pickup listings.
Historical address JSON remains untouched and is translated when read; existing
idempotency keys retain their original hashing rules.

This changes the API contracts: `/societies` becomes `/communities`, `/towers`
becomes `/zones`, `society_id` becomes `community_id`, `tower_id` becomes `zone_id`,
and `flat` becomes `address_label`. No legacy route aliases are provided. Regenerated
contracts are in `docs/openapi`; API consumers need to update alongside this backend.

Stop both APIs and the worker, back up the database, apply `uv run alembic upgrade head`,
then start the updated services together. The migration is forward-only because
new community hierarchies and fulfillment destinations cannot be represented by
the old schema. Rollback requires restoring the pre-migration database backup.

Optional push delivery commits each notification separately, releasing device
locks before claiming another notification. Delivery is at least once; clients
can deduplicate using the notification ID.

## Admin web app

The monochrome admin interface follows DevFeed's Next.js layout and API gateway
pattern. It uses atomic components, shadcn/ui, Tailwind, and Orval-generated
React Query hooks. See [admin development](apps/admin/README.md) for architecture,
authentication and runtime configuration.

```sh
npm ci
cp apps/admin/.env.example apps/admin/.env.local
npm run admin:dev
# After an API contract change:
npm run admin:generate
```

The UI uses port `3001`; the admin API uses `13001`. The configured admin origin
and Zitadel callback remain on the UI's port `3001`. Existing local environments
that use API port `3001` need to change `KITCHEN_ADMIN_API_PORT` to `13001` and set
`KITCHEN_ADMIN_WEB_PORT=3001` before starting both services.

## Validation

Tests need dedicated disposable PostgreSQL and Redis databases. The PostgreSQL
database name must end in `_test`; tests recreate its application tables. Use
Redis database 15 and no shared provider/session data.

```sh
uv run --no-sync python scripts/check_backend.py
uv run ruff check .
uv run ruff format --check .
uv run mypy -p kitchen_core -p kitchen_http -p kitchen_api -p kitchen_admin_api -p kitchen_worker
uv run python scripts/export_openapi.py
```

Install the commit hooks once per checkout:

```sh
uv sync --all-packages --locked
npm ci
uv run --no-sync pre-commit install
uv run --no-sync pre-commit run --all-files
```

Every commit runs Ruff lint and formatting checks, mypy, fresh/repeated Alembic
upgrades, schema comparison, and the full backend test suite. Admin changes also
run TypeScript checks. Hooks report failures without automatically fixing files.
The same backend hooks run in GitHub Actions; CI retains the admin build and
contract generation checks.

The backend hook starts disposable PostgreSQL 17 and Redis 8 containers on random
loopback ports and removes them, including their volumes, when checks finish.
Docker must be running; the first run downloads the images. Existing application
services and `.env` authentication settings are not used. To use your own dedicated
test services instead (both variables are required):

```sh
export KITCHEN_TEST_DATABASE_URL=postgresql+psycopg://kitchen:password@localhost:5432/kitchen_test
export KITCHEN_TEST_REDIS_URL=redis://localhost:6379/15
uv run --no-sync pre-commit run --all-files
```

Each run creates and removes a unique PostgreSQL schema so repeated runs start
fresh, including when explicit service URLs are supplied. These explicit services
must still be disposable: tests clear Redis database 15. A PostgreSQL name ending in `_test` and Redis
database 15 are enforced. Other contributors must install the hooks in their own
checkout; Git hooks are not installed by cloning.

Backend coverage measures every line and branch in `kitchen_core`, `kitchen_http`,
`kitchen_api`, `kitchen_admin_api`, and `kitchen_worker`, across unit and integration
tests. The full commit/CI suite requires 100% coverage. HTML, XML, and JSON reports
are written under `reports/`; open `reports/coverage-html/index.html` to inspect
individual files. The admin frontend, migrations, and repository scripts are
outside this Python application coverage target; migrations still run and are
validated separately before the test suite.

Integration tests cover concurrent reservations, checkout retries, stock
release, ownership and community boundaries, onboarding and the order lifecycle.
Auth tests use RSA-signed tokens from a mocked Zitadel provider with real Redis;
they do not claim a live sign-in against your Zitadel deployment.

## GitHub Actions

The workflows in `.github/workflows` follow DevFeed's pinned shared-workflow
pattern. `CI` runs on pull requests, merge queues, pushes to `master`, `v*` tags,
manual dispatch, and the weekly schedule. Configure branch protection to require
`CI required`; it fails when any required job fails or is skipped.

- Backend checks run Ruff, formatting, and mypy against the installed workspace
  packages. Integration tests use disposable PostgreSQL 17 (`kitchen_test`) and
  Redis 8 (database 15), with explicit test-only OIDC settings. A fresh database
  upgrade, repeated upgrade, and Alembic schema comparison run before pytest.
- Admin checks regenerate OpenAPI and Orval output, fail on generated-file drift,
  and build Next.js with its TypeScript checks. There is currently no frontend
  unit-test or ESLint suite; the workflow does not claim those checks.
- Security checks scan Git history for secrets, lint workflows, audit npm and uv
  dependencies, run extended CodeQL for Python, TypeScript, and Actions, and
  validate both Compose configurations using non-secret values.
- Container checks use `.github/images.json` to build the shared backend and
  standalone admin images on native ARM64 runners. The shared pipeline runs
  image smoke checks and vulnerability scans, generates SBOMs, and verifies
  published digests and attestations before promotion.

Image builds start only after backend, admin, and security checks pass. Publishing
is enabled only for pushes to `master` and version tags; PRs, merge queues,
scheduled runs, and manual runs only validate images. GHCR uses the repository's
`GITHUB_TOKEN` with job-scoped package write permission. Existing packages must
allow this repository to publish. For existing private packages without repository
access, the optional repository secret `GHCR_TOKEN` overrides registry authentication
only on trusted publishing pushes; PRs and validation runs receive no such secret.
Tags must match the version in `pyproject.toml`.
The pipeline does not update home-lab GitOps manifests or deploy the application.

Configure GitHub CodeQL as **advanced setup** to use these workflows. Use the
uploaded test reports, security reports, SBOMs, and image manifests to review a
run; a local check alone does not prove that the remote pipeline passed.

The backend image uses Python 3.12 on Alpine 3.23; locked native Python
wheels must support musl on ARM64. The admin runtime contains Node.js and the
standalone Next.js output, with package managers kept in the build stage.
Image smoke checks verify native backend imports and non-root execution.
Nested local `.env` files are excluded from every Docker build context.

## Mobile app

The Android/iOS Expo app lives in `apps/mobile`. It currently provides a themed navigation shell; login and ordering are not connected yet. See [mobile setup and stack decisions](apps/mobile/README.md) for development builds, checks, and maintenance.
