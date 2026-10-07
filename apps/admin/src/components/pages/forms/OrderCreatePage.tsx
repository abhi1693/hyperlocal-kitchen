"use client";
import { useEffect, useRef, useState } from "react";
import {
  adminOrderCreate,
  useAdminFoodKitchen,
  useAdminFoodKitchenListings,
} from "@/lib/api/generated/admin";
import type { AdminOrderCreate, ListingOut } from "@/lib/api/generated/models";
import { today, money, dateTime } from "@/lib/utils";
import { ResourceForm } from "@/components/organisms/resource-form";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { Combobox } from "@/components/molecules/combobox";
import { Field } from "@/components/molecules/field";
import { QueryState } from "@/components/molecules/query-state";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Textarea } from "@/components/atoms/textarea";

type BasketItem = { listing: ListingOut; quantity: number };
export function OrderCreatePage() {
  const [version, setVersion] = useState(0);
  return <Editor key={version} onCreateAnother={() => setVersion((v) => v + 1)} />;
}
function Editor({ onCreateAnother }: { onCreateAnother: () => void }) {
  const [kitchenId, setKitchenId] = useState("");
  const [date, setDate] = useState(today);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<BasketItem[]>([]);
  const [fulfillment, setFulfillment] = useState<"pickup" | "delivery">("pickup");
  const [point, setPoint] = useState("");
  const request = useRef<{ body: string; key: string }>(null);
  useEffect(() => {
    const timer = setTimeout(() => setQ(search), 250);
    return () => clearTimeout(timer);
  }, [search]);
  const kitchen = useAdminFoodKitchen(kitchenId, { query: { enabled: !!kitchenId } });
  const listings = useAdminFoodKitchenListings(
    kitchenId,
    { service_date: date, status: "published", q, limit: 30, offset },
    { query: { enabled: !!kitchenId && !!date } },
  );
  const options =
    listings.data?.items.filter(
      (row) =>
        row.is_orderable &&
        row.quantity_remaining > 0 &&
        !items.some((item) => item.listing.id === row.id) &&
        (!items.length ||
          (row.available_from === items[0].listing.available_from &&
            row.available_until === items[0].listing.available_until)),
    ) ?? [];
  const pickupAvailable =
    !!kitchen.data?.pickup_enabled &&
    items.length > 0 &&
    items.every((item) => item.listing.pickup_enabled);
  const deliveryAvailable =
    !!kitchen.data?.delivery_enabled &&
    items.length > 0 &&
    items.every((item) => item.listing.delivery_enabled);
  const points = items.length
    ? items[0].listing.pickup_points.filter(
        (candidate) =>
          candidate.active &&
          items.every((item) =>
            item.listing.pickup_points.some((p) => p.id === candidate.id && p.active),
          ),
      )
    : [];
  const subtotal = items.reduce((sum, item) => sum + item.listing.price_paise * item.quantity, 0);
  const deliveryFee = fulfillment === "delivery" ? (kitchen.data?.delivery_fee_paise ?? 0) : 0;
  const unavailable =
    !items.length ||
    !kitchen.data?.is_accepting_orders ||
    (fulfillment === "pickup" ? !pickupAvailable || !points.length : !deliveryAvailable);
  return (
    <ResourceForm
      title="New order"
      create
      cancelHref="/orders"
      description="Place an order on behalf of a community member."
      submitDisabled={unavailable}
      onCreateAnother={onCreateAnother}
      submit={(data) => {
        if (unavailable) throw new Error("Choose available items and a fulfillment option.");
        const payload: AdminOrderCreate = {
          customer_id: String(data.get("customer_id")),
          items: items
            .map((item) => ({
              menu_listing_id: item.listing.id,
              quantity: Number(data.get(`quantity_${item.listing.id}`)),
            }))
            .sort((a, b) => a.menu_listing_id.localeCompare(b.menu_listing_id)),
          fulfillment_type: fulfillment,
          customer_note: String(data.get("customer_note") ?? "").trim() || null,
          ...(fulfillment === "pickup"
            ? { pickup_point_id: String(data.get("pickup_point_id")) }
            : {
                delivery_address: {
                  zone_id: String(data.get("zone_id") ?? "") || null,
                  address_label: String(data.get("address_label")),
                },
              }),
        };
        const body = JSON.stringify(payload);
        if (request.current?.body !== body)
          request.current = {
            body,
            key: Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
              byte.toString(16).padStart(2, "0"),
            ).join(""),
          };
        return adminOrderCreate(payload, { headers: { "Idempotency-Key": request.current.key } });
      }}
    >
      <ReferencePicker
        kind="kitchen"
        name="kitchen_id"
        label="Kitchen"
        value={kitchenId}
        onChange={(next) => {
          setKitchenId(next);
          setItems([]);
          setPoint("");
          setSearch("");
          setOffset(0);
        }}
      />
      {kitchenId && (
        <QueryState
          pending={kitchen.isPending}
          error={kitchen.error}
          retry={() => kitchen.refetch()}
        />
      )}
      {kitchen.data && (
        <>
          {!kitchen.data.is_accepting_orders && (
            <p role="alert" className="text-sm">
              This kitchen is currently paused and cannot accept new orders.
            </p>
          )}
          <ReferencePicker
            key={kitchenId}
            kind="user"
            name="customer_id"
            label="Customer"
            communityId={kitchen.data.community_id}
          />
          <Field id="service_date" label="Service date">
            <Input
              id="service_date"
              type="date"
              required
              value={date}
              onChange={(event) => {
                setDate(event.target.value);
                setItems([]);
                setPoint("");
                setOffset(0);
              }}
            />
          </Field>
          <Field
            id="order_listing"
            label="Add dish"
            hint="Each order uses dishes from the same kitchen and ready window."
          >
            <Combobox
              id="order_listing"
              label="Add dish"
              disabled={items.length >= 50}
              value=""
              placeholder="Search published dishes…"
              options={options.map((row) => ({
                value: row.id,
                label: `${row.dish.name} · ${money(row.price_paise)} · ${row.quantity_remaining} available · ${dateTime(row.available_from)}`,
              }))}
              search={search}
              onSearchChange={(next) => {
                setSearch(next);
                setOffset(0);
              }}
              loading={listings.isFetching || search !== q}
              error={listings.error?.message}
              onRetry={() => listings.refetch()}
              onValueChange={(next) => {
                const listing = options.find((row) => row.id === next);
                if (listing) {
                  setItems((previous) => [...previous, { listing, quantity: 1 }]);
                  setPoint("");
                }
              }}
              footer={
                (listings.data?.total ?? 0) > 30 && (
                  <div className="flex items-center justify-between gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={!offset}
                      onClick={() => setOffset(Math.max(0, offset - 30))}
                    >
                      Previous
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      {offset + 1}–{Math.min(offset + 30, listings.data!.total)} of{" "}
                      {listings.data!.total}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={offset + 30 >= listings.data!.total}
                      onClick={() => setOffset(offset + 30)}
                    >
                      Next
                    </Button>
                  </div>
                )
              }
            />
          </Field>
        </>
      )}
      {items.length ? (
        <section aria-label="Order items" className="space-y-4 rounded-md border p-4">
          {items.map((item) => (
            <div
              key={item.listing.id}
              className="flex flex-wrap items-end gap-4 border-b pb-4 last:border-0 last:pb-0"
            >
              <div className="min-w-0 flex-1">
                <p className="font-medium">{item.listing.dish.name}</p>
                <p className="text-sm text-muted-foreground">
                  {money(item.listing.price_paise)} per portion · {item.listing.quantity_remaining}{" "}
                  available
                </p>
              </div>
              <div className="w-24">
                <Field id={`quantity_${item.listing.id}`} label="Portions">
                  <Input
                    id={`quantity_${item.listing.id}`}
                    name={`quantity_${item.listing.id}`}
                    type="number"
                    min="1"
                    max={Math.min(100, item.listing.quantity_remaining)}
                    required
                    value={Number.isNaN(item.quantity) ? "" : item.quantity}
                    onChange={(event) =>
                      setItems((previous) =>
                        previous.map((row) =>
                          row.listing.id === item.listing.id
                            ? { ...row, quantity: event.target.valueAsNumber }
                            : row,
                        ),
                      )
                    }
                  />
                </Field>
              </div>
              <Button
                variant="outline"
                size="sm"
                aria-label={`Remove ${item.listing.dish.name}`}
                onClick={() => {
                  setItems((previous) =>
                    previous.filter((row) => row.listing.id !== item.listing.id),
                  );
                  setPoint("");
                }}
              >
                Remove
              </Button>
            </div>
          ))}
        </section>
      ) : (
        <p className="text-sm text-muted-foreground">
          Choose a kitchen and add at least one available dish.
        </p>
      )}
      {items.length > 0 && (
        <>
          <Field id="fulfillment_type" label="Fulfillment">
            <Combobox
              id="fulfillment_type"
              name="fulfillment_type"
              label="Fulfillment"
              value={fulfillment}
              onValueChange={(next) => {
                setFulfillment(next as "pickup" | "delivery");
                setPoint("");
              }}
              options={[
                { value: "pickup", label: "Pickup" },
                { value: "delivery", label: "Home delivery" },
              ]}
            />
          </Field>
          {fulfillment === "pickup" ? (
            <>
              {(!pickupAvailable || !points.length) && (
                <p role="alert" className="text-sm">
                  The selected dishes do not share an available pickup point. Change the basket or
                  choose home delivery.
                </p>
              )}
              <Field id="pickup_point_id" label="Pickup point">
                <Combobox
                  id="pickup_point_id"
                  name="pickup_point_id"
                  label="Pickup point"
                  required
                  value={point}
                  onValueChange={setPoint}
                  options={points.map((row) => ({
                    value: row.id,
                    label: `${row.name} · ${row.address_label}`,
                  }))}
                />
              </Field>
            </>
          ) : (
            <>
              {!deliveryAvailable && (
                <p role="alert" className="text-sm">
                  Home delivery is not available for every selected dish.
                </p>
              )}
              <ReferencePicker
                key={kitchenId + "delivery"}
                kind="zone"
                name="zone_id"
                label="Delivery zone"
                communityId={kitchen.data?.community_id}
                required={false}
              />
              <Field id="delivery_address" label="Delivery address">
                <Input id="delivery_address" name="address_label" required maxLength={250} />
              </Field>
            </>
          )}
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt>Subtotal</dt>
              <dd>{money(Number.isFinite(subtotal) ? subtotal : 0)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Delivery fee</dt>
              <dd>{money(deliveryFee)}</dd>
            </div>
            <div className="flex justify-between gap-4 font-semibold">
              <dt>Estimated total</dt>
              <dd>{money((Number.isFinite(subtotal) ? subtotal : 0) + deliveryFee)}</dd>
            </div>
          </dl>
          <p className="text-sm text-muted-foreground">
            Final pricing and availability are confirmed when the order is placed. Payment goes
            directly to the kitchen.
          </p>
        </>
      )}
      <Field id="customer_note" label="Customer note (optional)">
        <Textarea id="customer_note" name="customer_note" maxLength={500} />
      </Field>
    </ResourceForm>
  );
}
