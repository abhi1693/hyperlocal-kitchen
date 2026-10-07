# Admin app

Next.js App Router administration app, adapted from DevFeed's admin layout,
server session and same-origin gateway pattern. The UI is monochrome and uses
standard shadcn primitives with Tailwind. DevFeed itself is not modified.

## Atomic component structure

- `src/components/atoms`: shadcn primitives and simple controls; the shadcn CLI
  maps its `ui` alias here through `components.json`.
- `src/components/molecules`: fields, filters, pagination, status, session and
  confirmation controls.
- `src/components/organisms`: reusable data tables, forms, header and navigation.
- `src/components/templates`: authenticated application layout.
- `src/components/pages`: resource screens composed from those pieces.
- `src/app`: thin App Router pages and the API gateway.
- `src/lib/api/generated`: committed Orval request functions, models, query keys
  and React Query hooks. Regenerate these instead of editing them.

Lists use generated query hooks. Reusable form/action organisms wrap generated
request functions in React Query mutations, invalidate affected live views after
success, and display API validation errors. Authentication uses server-validated
HttpOnly cookies; CSRF tokens are kept in memory, never in local storage.

## Local development

From the repository root:

```sh
npm ci
cp apps/admin/.env.example apps/admin/.env.local
npm run admin:dev
```

The UI runs at `http://localhost:3001`; its gateway targets the admin API at
`http://localhost:13001`. Run that API with the root Python environment and
configured PostgreSQL, Redis and Zitadel settings:

```sh
uv run alembic upgrade head
uv run uvicorn kitchen_admin_api.main:app --reload --port 13001 --no-access-log
```

The backend `KITCHEN_ADMIN_BASE_URL` and the UI's server-side
`KITCHEN_ADMIN_BASE_URL` must both be `http://localhost:3001`. Keep the Zitadel
callback at `http://localhost:3001/api/v1/auth/callback`: it now passes through the
UI gateway. The public admin origin is not the API's internal port. Production
requires explicit server-side API and public origins, HTTPS and secure cookies.

Docker Compose includes the admin app and forwards API traffic internally. If an
existing root `.env` sets `KITCHEN_ADMIN_API_PORT=3001`, change it to `13001` and add
`KITCHEN_ADMIN_WEB_PORT=3001`. Keep `KITCHEN_ADMIN_BASE_URL` on the UI origin.

## API generation

```sh
npm run admin:generate
```

This exports the backend contracts and generates the client from
`docs/openapi/admin.json`. Orval uses `react-query` with the fetch transport and a
custom cookie/CSRF mutator. API errors expose field messages in the forms. Never
replace a failed request with mock records or misleading counts.

## Current screens

Login, overview counts, communities and hierarchical zones, pickup points, users,
multi-community memberships, kitchen creation and approval, operators, pause and
resume, reusable dishes and Cook Again publication, dated menus, preparation
summaries with customer notes, searchable orders, fulfillment snapshots, lifecycle
controls and payment acknowledgement. Operational changes use ordinary
confirmation dialogs. Order data refreshes periodically while the page is visible.

Menu notification delivery, ratings, and reordering remain outside this slice.
The dedicated form routes are checked with a production build and browser
journeys against an isolated API fixture, covering save/cancel navigation,
validation, reloads, CSRF forwarding and responsive layouts.

## Create and edit pages

Forms use dedicated URLs, following DevFeed's admin pattern. List and detail
screens link to `/new` and `/edit` pages; zones, pickup points, dishes, listings
and operators sit under their parent community or kitchen. Approval, order
pausing and rejection also have their own form pages. Save returns to the
record or parent screen, Cancel leaves without saving, and create forms offer
“Create and add another”. Reloading an edit URL loads the current record from
the API. Validation errors keep the entered values on the page.


## Searchable choices

`Combobox` is the shared searchable control for enum choices, list filters and
API record pickers. Search runs locally for fixed choices and uses debounced API
queries for communities, users, zones and dishes. Keyboard selection, native
required validation and FormData preserve the underlying slugs/IDs. Record
pickers retain selected labels across search and pagination, and display loading,
empty and retry states inside the dropdown. Community filtering applies directly
without a dialog.


## User administration

`/users` links to `/users/[id]` profile pages with contact information, account
status, joined date and paginated community memberships. Dedicated `/edit`,
`/activate` and `/deactivate` pages return to that profile after saving. Membership
management links carry both `community_id` and `user_id` to keep the list scoped
to the selected user. Name and contact phone edits use the admin API. A dedicated `/delete` page removes
unused application profiles; linked records and the signed-in account are protected.
Zitadel accounts remain unchanged. Account creation remains with Zitadel sign-in,
and deactivation retains orders and history.


## Order administration

`/orders/new` creates an order on behalf of an active community member using
published, available dishes from one kitchen and ready window. The basket supports
quantities, pickup points shared by its dishes, home-delivery addresses, notes
and an estimated total. The API determines final prices and reserves inventory.
Identical retries reuse an idempotency key; a changed payload gets a new key.

Order detail screens link to `/edit` and dedicated lifecycle/payment pages.
Available edits follow the existing order state machine: accept, reject with a
reason, prepare, mark ready, complete, cancel, report payment and confirm payment.
Cancellation releases inventory while retaining order history. Completed items,
prices and fulfillment snapshots are not arbitrarily rewritten or deleted.
