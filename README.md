# Hyperlocal Kitchen

FastAPI backend for a private hyperlocal food marketplace for communities.
Members and kitchen owners share one account and one mobile API. Platform administration has
a separate API and Zitadel application. The admin web app and mobile UI come next.

## MVP

- Platform admins manage users, communities, zones, memberships, kitchens, dishes,
  dated listings and orders across communities. They approve kitchens and manage
  who can operate a kitchen.
- Members select a community and optionally provide a home zone and address label.
  Joining activates membership immediately, with no invitation or membership approval.
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

Docker Compose starts PostgreSQL, Redis, migrations, both APIs and the worker.
The project's local `.env` is configured for admin development. It selects
`compose.yaml` and `compose.build.yaml` through `COMPOSE_FILE`. Member API docs:
`http://localhost:18000/docs`. Platform-admin API docs:
`http://localhost:3001/docs`. `/health` reports process health; `/ready` checks
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

Run `uv run uvicorn kitchen_admin_api.main:app --reload --port 3001 --no-access-log` and
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
Serve the eventual web client and its API under the configured origin.

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
the contract for the future admin web app; exports live in `docs/openapi`.

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

## Client onboarding

The mobile and admin UIs are not implemented in this repository. Their contracts
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

## Validation

Tests need dedicated disposable PostgreSQL and Redis databases. The PostgreSQL
database name must end in `_test`; tests recreate its application tables. Use
Redis database 15 and no shared provider/session data.

```sh
KITCHEN_TEST_DATABASE_URL=postgresql+psycopg://kitchen:password@localhost:5432/kitchen_test \
KITCHEN_REDIS_URL=redis://localhost:6379/15 uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy -p kitchen_core -p kitchen_http -p kitchen_api -p kitchen_admin_api -p kitchen_worker
uv run python scripts/export_openapi.py
```

Integration tests cover concurrent reservations, checkout retries, stock
release, ownership and community boundaries, onboarding and the order lifecycle.
Auth tests use RSA-signed tokens from a mocked Zitadel provider with real Redis;
they do not claim a live sign-in against your Zitadel deployment.
