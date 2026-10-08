import { useState } from "react";
import { View } from "react-native";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Button,
  Checkbox,
  HelperText,
  RadioButton,
  Text,
  TextInput,
} from "react-native-paper";
import { useAuth } from "../auth/provider";
import type {
  CommunityZoneOut,
  DishCreate,
  DishOut,
  DishUpdate,
  KitchenCreate,
  KitchenOwnOut,
  KitchenUpdate,
  ListingCreate,
  ListingOut,
  ListingUpdate,
  MembershipOut,
  PickupPointCreate,
  PickupPointOut,
  PickupPointUpdate,
} from "../api/generated";
import {
  dishCreate,
  dishUpdate,
  indiaDate,
  indiaTime,
  kitchenCreate,
  kitchenUpdate,
  listingCreate,
  listingUpdate,
  paiseToRupees,
  pickupPointCreate,
  pickupPointUpdate,
  type DishForm,
  type KitchenForm,
  type ListingForm,
  type PickupPointForm,
} from "./forms";

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "Check the fields and try again.";
}

function FormActions({
  busy,
  onCancel,
  onSave,
  label,
}: {
  busy: boolean;
  onCancel?: () => void;
  onSave: () => void;
  label: string;
}) {
  return (
    <View style={{ gap: 8 }}>
      <Button mode="contained" loading={busy} disabled={busy} onPress={onSave}>
        {label}
      </Button>
      {onCancel && (
        <Button disabled={busy} onPress={onCancel}>
          Cancel
        </Button>
      )}
    </View>
  );
}

export function KitchenEditor({
  kitchen,
  membership,
  busy,
  onSave,
  onCancel,
  serverError,
}: {
  kitchen?: KitchenOwnOut;
  membership?: MembershipOut;
  busy: boolean;
  onSave: (body: KitchenCreate | KitchenUpdate) => void;
  onCancel?: () => void;
  serverError?: string | null;
}) {
  const { api, origin, user } = useAuth();
  const communityId = kitchen?.community_id ?? membership?.community_id;
  const [zoneId, setZoneId] = useState(
    kitchen ? (kitchen.zone_id ?? null) : (membership?.zone_id ?? null),
  );
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<KitchenForm>(() => ({
    name: kitchen?.name ?? "",
    description: kitchen?.description ?? "",
    addressLabel: kitchen ? (kitchen.address_label ?? "") : (membership?.address_label ?? ""),
    upiId: kitchen?.upi_id ?? "",
    fssaiNumber: kitchen?.fssai_number ?? "",
    deliveryFee: paiseToRupees(kitchen?.delivery_fee_paise ?? 0),
    pickupEnabled: kitchen?.pickup_enabled ?? true,
    deliveryEnabled: kitchen?.delivery_enabled ?? false,
  }));
  const zones = useInfiniteQuery({
    queryKey: ["kitchen-zones", origin, user?.id, communityId],
    enabled: !!communityId,
    networkMode: "always",
    retry: false,
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api<CommunityZoneOut[]>(
        `/api/v1/communities/${communityId}/zones?limit=100&offset=${pageParam}`,
      ),
    getNextPageParam: (page, _pages, offset) => (page.length === 100 ? offset + 100 : undefined),
  });
  const availableZones = zones.data?.pages.flat().filter((zone) => zone.active) ?? [];
  const field = <K extends keyof KitchenForm>(key: K, value: KitchenForm[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setError(null);
  };
  const submit = () => {
    try {
      if (!communityId) throw new Error("Join a community before creating a kitchen.");
      const body = kitchen ? kitchenUpdate(form) : kitchenCreate(form, communityId, zoneId);
      if (kitchen && zoneId !== (kitchen.zone_id ?? null)) body.zone_id = zoneId;
      setError(null);
      onSave(body);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };
  return (
    <View style={{ gap: 16 }}>
      <Text variant="titleLarge">{kitchen ? "Edit kitchen" : "Set up your kitchen"}</Text>
      <Text variant="bodyMedium">{kitchen?.community_name ?? membership?.community_name}</Text>
      <TextInput
        mode="outlined"
        label="Kitchen name"
        value={form.name}
        disabled={busy}
        onChangeText={(value) => field("name", value)}
      />
      <TextInput
        mode="outlined"
        label="About your kitchen (optional)"
        multiline
        value={form.description}
        disabled={busy}
        onChangeText={(value) => field("description", value)}
      />
      <TextInput
        mode="outlined"
        label="Kitchen address (optional)"
        multiline
        value={form.addressLabel}
        disabled={busy}
        onChangeText={(value) => field("addressLabel", value)}
      />
      <Text variant="bodySmall">Add a real pickup address before offering meals for pickup.</Text>
      <Text variant="titleMedium">Tower, block or area</Text>
      {zones.isPending && <ActivityIndicator accessibilityLabel="Loading kitchen areas" />}
      {zones.error && (
        <>
          <HelperText type="error" visible>
            Could not load areas. You can keep your current area or try again.
          </HelperText>
          <Button disabled={zones.isFetching} onPress={() => void zones.refetch()}>
            Retry areas
          </Button>
        </>
      )}
      <RadioButton.Group
        value={zoneId ?? ""}
        onValueChange={(value) => {
          setZoneId(value || null);
          setError(null);
        }}
      >
        <RadioButton.Item label="No specific area" value="" disabled={busy} />
        {availableZones.map((zone) => (
          <RadioButton.Item key={zone.id} label={zone.name} value={zone.id} disabled={busy} />
        ))}
      </RadioButton.Group>
      {zones.hasNextPage && (
        <Button
          disabled={zones.isFetchingNextPage}
          loading={zones.isFetchingNextPage}
          onPress={() => void zones.fetchNextPage()}
        >
          More areas
        </Button>
      )}
      <Text variant="titleMedium">Fulfillment</Text>
      <Checkbox.Item
        label="Offer pickup"
        status={form.pickupEnabled ? "checked" : "unchecked"}
        disabled={busy}
        onPress={() => field("pickupEnabled", !form.pickupEnabled)}
      />
      <Checkbox.Item
        label="Offer delivery"
        status={form.deliveryEnabled ? "checked" : "unchecked"}
        disabled={busy}
        onPress={() => field("deliveryEnabled", !form.deliveryEnabled)}
      />
      {form.deliveryEnabled && (
        <TextInput
          mode="outlined"
          label="Delivery fee (₹)"
          keyboardType="decimal-pad"
          value={form.deliveryFee}
          disabled={busy}
          onChangeText={(value) => field("deliveryFee", value)}
        />
      )}
      <TextInput
        mode="outlined"
        label="UPI ID (optional)"
        autoCapitalize="none"
        value={form.upiId}
        disabled={busy}
        onChangeText={(value) => field("upiId", value)}
      />
      <TextInput
        mode="outlined"
        label="FSSAI number (14 digits, optional during setup)"
        keyboardType="number-pad"
        value={form.fssaiNumber}
        disabled={busy}
        onChangeText={(value) => field("fssaiNumber", value)}
      />
      {!kitchen && (
        <Text variant="bodyMedium">
          Your kitchen starts pending approval. You can prepare items and draft menus while the
          platform admin reviews it.
        </Text>
      )}
      {(error || serverError) && (
        <HelperText type="error" visible accessibilityLiveRegion="polite">
          {error || serverError}
        </HelperText>
      )}
      <FormActions
        busy={busy}
        onCancel={onCancel}
        onSave={submit}
        label={kitchen ? "Save kitchen" : "Create kitchen"}
      />
    </View>
  );
}

export function DishEditor({
  dish,
  busy,
  onSave,
  onCancel,
  serverError,
}: {
  dish?: DishOut;
  busy: boolean;
  onSave: (body: DishCreate | DishUpdate) => void;
  onCancel: () => void;
  serverError?: string | null;
}) {
  const [form, setForm] = useState<DishForm>(() => ({
    name: dish?.name ?? "",
    description: dish?.description ?? "",
    imageUrl: dish?.image_url ?? "",
  }));
  const [error, setError] = useState<string | null>(null);
  const field = (key: keyof DishForm, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
    setError(null);
  };
  const submit = () => {
    try {
      const body = dish ? dishUpdate(form) : dishCreate(form);
      setError(null);
      onSave(body);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };
  return (
    <View style={{ gap: 16 }}>
      <Text variant="titleLarge">{dish ? "Edit item" : "New item"}</Text>
      <TextInput
        mode="outlined"
        label="Item name"
        value={form.name}
        disabled={busy}
        onChangeText={(value) => field("name", value)}
      />
      <TextInput
        mode="outlined"
        label="Description (optional)"
        multiline
        value={form.description}
        disabled={busy}
        onChangeText={(value) => field("description", value)}
      />
      <TextInput
        mode="outlined"
        label="Photo link (optional)"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        value={form.imageUrl}
        disabled={busy}
        onChangeText={(value) => field("imageUrl", value)}
      />
      <Text variant="bodySmall">
        Use a public HTTPS photo link. You can reuse this item in menus for different days.
      </Text>
      {(error || serverError) && (
        <HelperText type="error" visible accessibilityLiveRegion="polite">
          {error || serverError}
        </HelperText>
      )}
      <FormActions
        busy={busy}
        onCancel={onCancel}
        onSave={submit}
        label={dish ? "Save item" : "Create item"}
      />
    </View>
  );
}

export function PickupEditor({
  point,
  kitchen,
  busy,
  onSave,
  onCancel,
  serverError,
}: {
  point?: PickupPointOut;
  kitchen: KitchenOwnOut;
  busy: boolean;
  onSave: (body: PickupPointCreate | PickupPointUpdate) => void;
  onCancel: () => void;
  serverError?: string | null;
}) {
  const [form, setForm] = useState<PickupPointForm>(() => ({
    name: point?.name ?? "Kitchen pickup",
    addressLabel: point?.address_label ?? kitchen.address_label ?? "",
    instructions: point?.instructions ?? "",
  }));
  const [error, setError] = useState<string | null>(null);
  const field = (key: keyof PickupPointForm, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
    setError(null);
  };
  const submit = () => {
    try {
      const body = point ? pickupPointUpdate(form) : pickupPointCreate(form);
      if (!point) body.zone_id = kitchen.zone_id ?? null;
      setError(null);
      onSave(body);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };
  return (
    <View style={{ gap: 16 }}>
      <Text variant="titleLarge">{point ? "Edit pickup point" : "Add pickup point"}</Text>
      <TextInput
        mode="outlined"
        label="Pickup point name"
        value={form.name}
        disabled={busy}
        onChangeText={(value) => field("name", value)}
      />
      <TextInput
        mode="outlined"
        label="Pickup address"
        multiline
        value={form.addressLabel}
        disabled={busy}
        onChangeText={(value) => field("addressLabel", value)}
      />
      <TextInput
        mode="outlined"
        label="Pickup instructions (optional)"
        multiline
        value={form.instructions}
        disabled={busy}
        onChangeText={(value) => field("instructions", value)}
      />
      <Text variant="bodySmall">
        Give residents a real address where they can collect their meals.
      </Text>
      {(error || serverError) && (
        <HelperText type="error" visible accessibilityLiveRegion="polite">
          {error || serverError}
        </HelperText>
      )}
      <FormActions
        busy={busy}
        onCancel={onCancel}
        onSave={submit}
        label={point ? "Save pickup point" : "Add pickup point"}
      />
    </View>
  );
}

function initialListing(
  kitchen: KitchenOwnOut,
  points: PickupPointOut[],
  date: string,
  listing?: ListingOut,
): ListingForm {
  if (listing)
    return {
      dishId: listing.dish.id,
      serviceDate: listing.service_date,
      readyFrom: indiaTime(new Date(listing.available_from)),
      readyUntil: indiaTime(new Date(listing.available_until)),
      readyUntilDate: indiaDate(new Date(listing.available_until)),
      cutoff: indiaTime(new Date(listing.order_cutoff)),
      cutoffDate: indiaDate(new Date(listing.order_cutoff)),
      price: paiseToRupees(listing.price_paise),
      quantity: String(listing.quantity_total),
      pickupEnabled: listing.pickup_enabled,
      deliveryEnabled: listing.delivery_enabled,
      pickupPointIds: listing.pickup_points.map((point) => point.id),
      status: listing.status === "draft" ? "draft" : "published",
    };
  const now = new Date();
  const start = new Date(now.getTime() + 60 * 60_000);
  const end = new Date(now.getTime() + 180 * 60_000);
  const cutoff = new Date(now.getTime() + 45 * 60_000);
  const today = date === indiaDate(now);
  const defaultPoint = points.find((point) => point.active);
  return {
    dishId: "",
    serviceDate: today ? indiaDate(start) : date,
    readyFrom: today ? indiaTime(start) : "12:00",
    readyUntil: today ? indiaTime(end) : "14:00",
    readyUntilDate: today ? indiaDate(end) : date,
    cutoff: today ? indiaTime(cutoff) : "11:30",
    cutoffDate: today ? indiaDate(cutoff) : date,
    price: "",
    quantity: "",
    pickupEnabled: kitchen.pickup_enabled,
    deliveryEnabled: kitchen.delivery_enabled,
    pickupPointIds: kitchen.pickup_enabled && defaultPoint ? [defaultPoint.id] : [],
    status: "draft",
  };
}

export function ListingEditor({
  kitchen,
  listing,
  dishes,
  points,
  date,
  busy,
  moreDishes,
  onMoreDishes,
  loadingDishes,
  onSave,
  onCancel,
  onAddPickup,
  serverError,
  sharedPointsError,
  loadingSharedPoints,
  onRetrySharedPoints,
}: {
  kitchen: KitchenOwnOut;
  listing?: ListingOut;
  dishes: DishOut[];
  points: PickupPointOut[];
  date: string;
  busy: boolean;
  moreDishes: boolean;
  onMoreDishes: () => void;
  loadingDishes: boolean;
  onSave: (body: ListingCreate | ListingUpdate) => void;
  onCancel: () => void;
  onAddPickup: () => void;
  serverError?: string | null;
  sharedPointsError?: string | null;
  loadingSharedPoints: boolean;
  onRetrySharedPoints: () => void;
}) {
  // A listing includes its selected shared points even if a directory read fails.
  // Fresh directory metadata takes precedence, including inactive own points.
  const availablePoints = Array.from(
    new Map(
      [...(listing?.pickup_points ?? []), ...points].map((point) => [point.id, point]),
    ).values(),
  );
  const [form, setForm] = useState<ListingForm>(() =>
    initialListing(kitchen, points, date, listing),
  );
  const [error, setError] = useState<string | null>(null);
  const field = <K extends keyof ListingForm>(key: K, value: ListingForm[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setError(null);
  };
  const submit = (status: "draft" | "published") => {
    try {
      const savedPoints = listing?.pickup_points.map((point) => point.id) ?? [];
      const selectedPoints = form.pickupPointIds ?? [];
      const unchangedPickup =
        !!listing &&
        form.pickupEnabled === listing.pickup_enabled &&
        savedPoints.length === selectedPoints.length &&
        savedPoints.every((id) => selectedPoints.includes(id));
      if (
        form.pickupEnabled &&
        !unchangedPickup &&
        (!selectedPoints.length ||
          selectedPoints.some(
            (id) => !availablePoints.some((point) => point.id === id && point.active),
          ))
      )
        throw new Error(
          "Choose active pickup points. Remove unavailable points or add a new one first.",
        );
      const context = {
        kitchen,
        existingStatus: listing?.status === "sold_out" ? "published" : listing?.status,
      };
      const values = { ...form, status };
      const body = listing
        ? listingUpdate(values, context, listing)
        : listingCreate(values, context);
      setError(null);
      onSave(body);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };
  const activePoints = availablePoints.filter((point) => point.active);
  const unavailablePoints = (form.pickupPointIds ?? []).filter(
    (id) => !activePoints.some((point) => point.id === id),
  );
  return (
    <View style={{ gap: 16 }}>
      <Text variant="titleLarge">{listing ? "Edit menu item" : "Add item to menu"}</Text>
      {listing ? (
        <Text variant="titleMedium">{listing.dish.name}</Text>
      ) : (
        <>
          <Text variant="titleMedium">Choose an item</Text>
          <RadioButton.Group value={form.dishId} onValueChange={(value) => field("dishId", value)}>
            {dishes
              .filter((dish) => dish.is_active)
              .map((dish) => (
                <RadioButton.Item key={dish.id} label={dish.name} value={dish.id} disabled={busy} />
              ))}
          </RadioButton.Group>
          {moreDishes && (
            <Button disabled={loadingDishes} loading={loadingDishes} onPress={onMoreDishes}>
              More items
            </Button>
          )}
        </>
      )}
      <TextInput
        mode="outlined"
        label="Service date (YYYY-MM-DD)"
        maxLength={10}
        value={form.serviceDate}
        disabled={busy}
        onChangeText={(value) => {
          field("serviceDate", value);
          field("readyUntilDate", value);
          field("cutoffDate", value);
        }}
      />
      <Text variant="bodySmall">All times below use India time, in 24-hour format.</Text>
      <TextInput
        mode="outlined"
        label="Ready from (HH:mm)"
        maxLength={5}
        value={form.readyFrom}
        disabled={busy}
        onChangeText={(value) => field("readyFrom", value)}
      />
      <TextInput
        mode="outlined"
        label="Ready until date (YYYY-MM-DD)"
        maxLength={10}
        value={form.readyUntilDate ?? form.serviceDate}
        disabled={busy}
        onChangeText={(value) => field("readyUntilDate", value)}
      />
      <TextInput
        mode="outlined"
        label="Ready until (HH:mm)"
        maxLength={5}
        value={form.readyUntil}
        disabled={busy}
        onChangeText={(value) => field("readyUntil", value)}
      />
      <TextInput
        mode="outlined"
        label="Order cutoff date (YYYY-MM-DD)"
        maxLength={10}
        value={form.cutoffDate ?? form.serviceDate}
        disabled={busy}
        onChangeText={(value) => field("cutoffDate", value)}
      />
      <TextInput
        mode="outlined"
        label="Order cutoff (HH:mm)"
        maxLength={5}
        value={form.cutoff}
        disabled={busy}
        onChangeText={(value) => field("cutoff", value)}
      />
      <TextInput
        mode="outlined"
        label="Price per portion (₹)"
        keyboardType="decimal-pad"
        value={form.price}
        disabled={busy}
        onChangeText={(value) => field("price", value)}
      />
      <TextInput
        mode="outlined"
        label="Total portions"
        keyboardType="number-pad"
        value={form.quantity}
        disabled={busy}
        onChangeText={(value) => field("quantity", value)}
      />
      {listing && (
        <Text variant="bodySmall">
          {listing.quantity_total - listing.quantity_remaining} portions are reserved. Existing
          orders may limit changes to this listing.
        </Text>
      )}
      <Checkbox.Item
        label="Pickup"
        status={form.pickupEnabled ? "checked" : "unchecked"}
        disabled={busy || (!kitchen.pickup_enabled && !form.pickupEnabled)}
        onPress={() => {
          field("pickupEnabled", !form.pickupEnabled);
          field(
            "pickupPointIds",
            form.pickupEnabled ? [] : activePoints.length ? [activePoints[0].id] : [],
          );
        }}
      />
      <Checkbox.Item
        label="Delivery"
        status={form.deliveryEnabled ? "checked" : "unchecked"}
        disabled={busy || (!kitchen.delivery_enabled && !form.deliveryEnabled)}
        onPress={() => field("deliveryEnabled", !form.deliveryEnabled)}
      />
      {form.deliveryEnabled && (
        <Text variant="bodySmall">
          Kitchen delivery fee: ₹{(kitchen.delivery_fee_paise / 100).toFixed(2)}
        </Text>
      )}
      {form.pickupEnabled && (
        <>
          <Text variant="titleMedium">Pickup points</Text>
          {loadingSharedPoints && (
            <ActivityIndicator accessibilityLabel="Loading community pickup choices" />
          )}
          {sharedPointsError && (
            <>
              <HelperText type="error" visible accessibilityLiveRegion="polite">
                Could not load community pickup points. {sharedPointsError}
              </HelperText>
              <Button
                disabled={busy || loadingSharedPoints}
                loading={loadingSharedPoints}
                onPress={onRetrySharedPoints}
              >
                Retry community pickup points
              </Button>
            </>
          )}
          {listing?.pickup_enabled && (
            <Text variant="bodySmall">
              Existing pickup arrangements stay unchanged until you change the selected points.
              Stock changes can keep those arrangements.
            </Text>
          )}
          {!activePoints.length && (
            <HelperText type="info" visible>
              Add a pickup point with a real address to offer a new pickup arrangement.
            </HelperText>
          )}
          {activePoints.map((point) => (
            <Checkbox.Item
              key={point.id}
              label={`${point.name}${point.kitchen_id === null ? " (community)" : ""}: ${point.address_label}`}
              status={form.pickupPointIds?.includes(point.id) ? "checked" : "unchecked"}
              disabled={busy}
              onPress={() =>
                field(
                  "pickupPointIds",
                  form.pickupPointIds?.includes(point.id)
                    ? form.pickupPointIds.filter((id) => id !== point.id)
                    : [...(form.pickupPointIds ?? []), point.id],
                )
              }
            />
          ))}
          {unavailablePoints.map((id) => (
            <Checkbox.Item
              key={id}
              label={`${availablePoints.find((point) => point.id === id)?.name ?? "Previously selected pickup point"} (unavailable; remove)`}
              status="checked"
              disabled={busy}
              onPress={() =>
                field(
                  "pickupPointIds",
                  form.pickupPointIds?.filter((pointId) => pointId !== id) ?? [],
                )
              }
            />
          ))}
          <Button disabled={busy} onPress={onAddPickup}>
            Add pickup point
          </Button>
        </>
      )}
      {kitchen.status !== "approved" && (
        <HelperText type="info" visible>
          Save a draft now. Publishing requires platform approval for your kitchen.
        </HelperText>
      )}
      {(error || serverError) && (
        <HelperText type="error" visible accessibilityLiveRegion="polite">
          {error || serverError}
        </HelperText>
      )}
      {listing?.status !== "published" && listing?.status !== "sold_out" && (
        <Button mode="outlined" disabled={busy} loading={busy} onPress={() => submit("draft")}>
          Save draft
        </Button>
      )}
      <Button
        mode="contained"
        disabled={busy || kitchen.status !== "approved"}
        loading={busy}
        onPress={() => submit("published")}
      >
        {listing?.status === "published" || listing?.status === "sold_out"
          ? "Save published item"
          : "Publish item"}
      </Button>
      <Button disabled={busy} onPress={onCancel}>
        Cancel editing
      </Button>
    </View>
  );
}
