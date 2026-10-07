"use client";
import { useEffect, useState } from "react";
import {
  useAdminFoodKitchenDishes,
  useAdminGetCommunity,
  useCommunityPickupPointsApiV1CommunitiesCommunityIdPickupPointsGet,
  adminFoodCreateKitchenListing,
} from "@/lib/api/generated/admin";
import type { DishOut, KitchenOwnOut } from "@/lib/api/generated/models";
import { today } from "@/lib/utils";
import { Field } from "@/components/molecules/field";
import { QueryState } from "@/components/molecules/query-state";
import { Input } from "@/components/atoms/input";
import { Combobox } from "@/components/molecules/combobox";
import { Button } from "@/components/atoms/button";
import { ResourceForm } from "./resource-form";
export function ListingForm({
  kitchen,
  dish,
  date,
}: {
  kitchen: KitchenOwnOut;
  dish?: DishOut;
  date?: string;
}) {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setQ(search), 250);
    return () => clearTimeout(timer);
  }, [search]);
  const dishes = useAdminFoodKitchenDishes(kitchen.id, {
    is_active: true,
    q,
    limit: 30,
    offset,
  });
  const community = useAdminGetCommunity(kitchen.community_id);
  const points = useCommunityPickupPointsApiV1CommunitiesCommunityIdPickupPointsGet(
    kitchen.community_id,
  );
  const eligible =
    points.data?.filter(
      (point) =>
        point.active &&
        (!point.kitchen_id || point.kitchen_id === kitchen.id) &&
        (!point.zone_id ||
          community.data?.zones.some((zone) => zone.id === point.zone_id && zone.active)),
    ) ?? [];
  return (
    <ResourceForm
      create
      cancelHref={`/kitchens/${kitchen.id}`}
      title={dish ? `Cook again: ${dish.name}` : "Publish a listing"}
      description="All dates and times use India time (IST)."
      submit={(data) => {
        const date = String(data.get("service_date"));
        return adminFoodCreateKitchenListing(kitchen.id, {
          dish_id: dish?.id ?? String(data.get("dish_id")),
          service_date: date,
          available_from: `${date}T${data.get("from_time")}:00+05:30`,
          available_until: `${date}T${data.get("until_time")}:00+05:30`,
          order_cutoff: `${data.get("order_cutoff")}:00+05:30`,
          quantity_total: Number(data.get("quantity")),
          price_paise: Math.round(Number(data.get("price")) * 100),
          pickup_enabled: data.has("pickup_enabled"),
          delivery_enabled: data.has("delivery_enabled"),
          pickup_point_ids: data.has("pickup_enabled")
            ? data.getAll("pickup_point_ids").map(String)
            : [],
          status: "published",
        });
      }}
    >
      {!dish && (
        <Field id="dish_id" label="Dish">
          <Combobox
            label="Dish"
            id="dish_id"
            name="dish_id"
            required
            search={search}
            onSearchChange={(next) => {
              setSearch(next);
              setOffset(0);
            }}
            loading={dishes.isFetching || search !== q}
            error={dishes.error?.message}
            onRetry={() => dishes.refetch()}
            defaultValue=""
            options={dishes.data?.items.map((row) => ({ value: row.id, label: row.name })) ?? []}
            footer={
              (dishes.data?.total ?? 0) > 30 && (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - 30))}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={offset + 30 >= dishes.data!.total}
                    onClick={() => setOffset(offset + 30)}
                  >
                    Next
                  </Button>
                </div>
              )
            }
          />
        </Field>
      )}
      <Field id="service_date" label="Service date">
        <Input
          id="service_date"
          name="service_date"
          type="date"
          required
          defaultValue={date ?? today()}
        />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field id="quantity" label="Portions">
          <Input
            id="quantity"
            name="quantity"
            type="number"
            min="1"
            max="10000"
            required
            defaultValue="15"
          />
        </Field>
        <Field id="price" label="Price per portion (₹)">
          <Input
            id="price"
            name="price"
            type="number"
            min="0.01"
            max="100000"
            step="0.01"
            required
          />
        </Field>
      </div>
      <Field id="order_cutoff" label="Orders close (IST)">
        <Input
          id="order_cutoff"
          name="order_cutoff"
          type="datetime-local"
          required
          defaultValue={`${date ?? today()}T11:30`}
        />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field id="from_time" label="Ready from (IST)">
          <Input id="from_time" name="from_time" type="time" required defaultValue="12:00" />
        </Field>
        <Field id="until_time" label="Ready until (IST)">
          <Input id="until_time" name="until_time" type="time" required defaultValue="13:00" />
        </Field>
      </div>
      <div className="flex gap-6">
        <label className="flex items-center gap-2 text-sm">
          <Input
            type="checkbox"
            name="pickup_enabled"
            defaultChecked={kitchen.pickup_enabled}
            disabled={!kitchen.pickup_enabled}
          />
          Pickup
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Input
            type="checkbox"
            name="delivery_enabled"
            defaultChecked={!kitchen.pickup_enabled && kitchen.delivery_enabled}
            disabled={!kitchen.delivery_enabled}
          />
          Delivery
        </label>
      </div>
      {kitchen.pickup_enabled && (
        <div className="space-y-2">
          <p className="text-sm font-medium">Pickup points</p>
          <p className="text-xs text-muted-foreground">
            Choose collection locations. If none is selected, the kitchen’s default eligible point
            is used.
          </p>
          <QueryState
            pending={points.isPending || community.isPending}
            error={points.error ?? community.error}
            retry={() => {
              points.refetch();
              community.refetch();
            }}
          />
          {eligible.map((point) => (
            <label key={point.id} className="flex items-center gap-2 text-sm">
              <Input type="checkbox" name="pickup_point_ids" value={point.id} />
              {point.name} · {point.address_label}
            </label>
          ))}
        </div>
      )}
    </ResourceForm>
  );
}
