import { useLayoutEffect, useRef, useState } from "react";
import { View } from "react-native";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Button,
  Card,
  Chip,
  Dialog,
  HelperText,
  Portal,
  SegmentedButtons,
  Text,
  TextInput,
} from "react-native-paper";
import { Screen } from "../components/screen";
import { AuthError } from "../auth/client";
import { useAuth } from "../auth/provider";
import { useExperience } from "../experience/provider";
import { useOnboarding } from "../onboarding/provider";
import type {
  DishCreate,
  DishOut,
  DishUpdate,
  KitchenCreate,
  KitchenOwnOut,
  KitchenUpdate,
  ListingCreate,
  ListingOut,
  ListingPage,
  ListingUpdate,
  PickupPointCreate,
  PickupPointOut,
  PickupPointUpdate,
} from "../api/generated";
import { DishEditor, KitchenEditor, ListingEditor, PickupEditor } from "./editors";
import { indiaDate, indiaTime, validDate } from "./forms";

const PAGE_SIZE = 20;
function failure(reason: unknown): string {
  return reason instanceof Error
    ? reason.message
    : "Could not save your changes. Please try again.";
}
function QueryFailure({
  error,
  retry,
  loading,
}: {
  error: unknown;
  retry: () => void;
  loading: boolean;
}) {
  if (!error) return null;
  return (
    <View accessibilityLiveRegion="polite">
      <HelperText type="error" visible>
        {failure(error)}
      </HelperText>
      <Button disabled={loading} loading={loading} onPress={retry}>
        Try again
      </Button>
    </View>
  );
}

export default function KitchenWorkspace() {
  const { user, origin } = useAuth();
  const { state } = useExperience();
  return <Workspace key={`${origin}:${user?.id}:${state?.owned_kitchen?.id ?? "new"}`} />;
}

function Workspace() {
  const { api, origin, user } = useAuth();
  const { state, refresh, saving } = useExperience();
  const { state: onboarding } = useOnboarding();
  const kitchen = state?.owned_kitchen;
  const membership = onboarding?.membership ?? undefined;
  const cache = useQueryClient();
  const key = ["kitchen-workspace", origin, user?.id, kitchen?.id] as const;
  const [section, setSection] = useState("kitchen");
  const [editingKitchen, setEditingKitchen] = useState(false);
  const [editingDish, setEditingDish] = useState<DishOut | null | undefined>();
  const [editingListing, setEditingListing] = useState<ListingOut | null | undefined>();
  const [editingPoint, setEditingPoint] = useState<PickupPointOut | null | undefined>();
  const [archiveDish, setArchiveDish] = useState<DishOut | null>(null);
  const [cancelListing, setCancelListing] = useState<ListingOut | null>(null);
  const [date, setDate] = useState(() => indiaDate());
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const mounted = useRef(true);
  const mutationLock = useRef(false);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const dishes = useInfiniteQuery({
    queryKey: [...key, "items"],
    enabled: !!kitchen,
    retry: false,
    networkMode: "always",
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api<DishOut[]>(
        `/api/v1/kitchens/${kitchen?.id}/dishes?limit=${PAGE_SIZE}&offset=${pageParam}`,
      ),
    getNextPageParam: (page, _pages, offset) =>
      page.length === PAGE_SIZE ? offset + PAGE_SIZE : undefined,
  });
  const points = useQuery({
    queryKey: [...key, "pickup-points"],
    enabled: !!kitchen,
    retry: false,
    networkMode: "always",
    queryFn: () => api<PickupPointOut[]>(`/api/v1/kitchens/${kitchen?.id}/pickup-points`),
  });
  const sharedPoints = useQuery({
    queryKey: [...key, "community-pickup-points", kitchen?.community_id],
    enabled: !!kitchen,
    retry: false,
    networkMode: "always",
    queryFn: () =>
      api<PickupPointOut[]>(`/api/v1/communities/${kitchen?.community_id}/pickup-points`),
  });
  const menus = useInfiniteQuery({
    queryKey: [...key, "menus", date],
    enabled: !!kitchen && validDate(date),
    retry: false,
    networkMode: "always",
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api<ListingPage>(
        `/api/v1/kitchens/${kitchen?.id}/menu-listings?date=${encodeURIComponent(date)}&limit=${PAGE_SIZE}&offset=${pageParam}`,
      ),
    getNextPageParam: (page) => {
      const next = page.offset + page.items.length;
      return page.items.length && next < page.total ? next : undefined;
    },
  });
  const items = dishes.data?.pages.flat() ?? [];
  const pickupPoints = Array.from(
    new Map(
      [
        ...(sharedPoints.data ?? []).filter((point) => point.kitchen_id === null && point.active),
        ...(points.data ?? []),
      ].map((point) => [point.id, point]),
    ).values(),
  );
  const listings = menus.data?.pages.flatMap((page) => page.items) ?? [];
  const operation = useMutation({
    retry: false,
    networkMode: "always",
    mutationFn: (work: () => Promise<string>) => work(),
    onSuccess: (message) => {
      if (mounted.current) setSuccess(message);
    },
    onError: (reason) => {
      if (mounted.current) setError(failure(reason));
    },
  });
  const busy = operation.isPending || saving;
  const suspended = kitchen?.status === "suspended";
  const run = (work: () => Promise<string>) => {
    if (mutationLock.current || saving) return;
    mutationLock.current = true;
    setError(null);
    setSuccess(null);
    operation.mutate(work, {
      onSettled: () => {
        mutationLock.current = false;
      },
    });
  };
  const assertCurrent = () => {
    if (!mounted.current) throw new AuthError("Your session changed. Please try again.");
  };
  const reload = async () => {
    assertCurrent();
    await cache.invalidateQueries({ queryKey: key });
  };
  const saveKitchen = (body: KitchenCreate | KitchenUpdate) =>
    run(async () => {
      if (kitchen) {
        await api<KitchenOwnOut>(`/api/v1/kitchens/${kitchen.id}`, { method: "PATCH", body });
      } else {
        try {
          await api<KitchenOwnOut>("/api/v1/kitchens", { method: "POST", body });
        } catch (reason) {
          if (reason instanceof AuthError && reason.status === 401) throw reason;
          assertCurrent();
          try {
            const recovered = await api<{ owned_kitchen: KitchenOwnOut | null }>(
              "/api/v1/me/experience",
            );
            if (!recovered.owned_kitchen) throw reason;
          } catch {
            throw reason;
          }
        }
      }
      assertCurrent();
      await refresh();
      if (mounted.current) setEditingKitchen(false);
      return kitchen
        ? "Kitchen saved."
        : "Kitchen created. You can now prepare items and menu drafts.";
    });
  const saveDish = (body: DishCreate | DishUpdate) =>
    run(async () => {
      if (!kitchen) throw new Error("Create your kitchen first.");
      await api<DishOut>(
        editingDish ? `/api/v1/dishes/${editingDish.id}` : `/api/v1/kitchens/${kitchen.id}/dishes`,
        {
          method: editingDish ? "PATCH" : "POST",
          body,
        },
      );
      await reload();
      if (mounted.current) setEditingDish(undefined);
      return "Item saved.";
    });
  const savePoint = (body: PickupPointCreate | PickupPointUpdate) =>
    run(async () => {
      if (!kitchen) throw new Error("Create your kitchen first.");
      await api<PickupPointOut>(
        `/api/v1/kitchens/${kitchen.id}/pickup-points${editingPoint ? "/" + editingPoint.id : ""}`,
        {
          method: editingPoint ? "PATCH" : "POST",
          body,
        },
      );
      await reload();
      if (mounted.current) setEditingPoint(undefined);
      return "Pickup point saved.";
    });
  const saveListing = (body: ListingCreate | ListingUpdate) =>
    run(async () => {
      if (!kitchen) throw new Error("Create your kitchen first.");
      const result = await api<ListingOut>(
        editingListing
          ? `/api/v1/menu-listings/${editingListing.id}`
          : `/api/v1/kitchens/${kitchen.id}/menu-listings`,
        {
          method: editingListing ? "PATCH" : "POST",
          body,
        },
      );
      await reload();
      if (mounted.current) {
        setEditingListing(undefined);
        setDate(result.service_date);
      }
      return result.status === "draft" ? "Menu draft saved." : "Menu item published.";
    });

  return (
    <Screen
      title={kitchen?.name ?? "Your kitchen"}
      subtitle="Manage your kitchen, reusable food items and daily menus."
    >
      {error && (
        <HelperText type="error" visible accessibilityLiveRegion="polite">
          {error}
        </HelperText>
      )}
      {success && (
        <HelperText type="info" visible accessibilityLiveRegion="polite">
          {success}
        </HelperText>
      )}
      {!kitchen ? (
        <Card mode="outlined">
          <Card.Content>
            {membership ? (
              <KitchenEditor
                membership={membership}
                busy={busy}
                onSave={saveKitchen}
                serverError={error}
              />
            ) : (
              <HelperText type="error" visible>
                Join a community before creating your kitchen.
              </HelperText>
            )}
          </Card.Content>
        </Card>
      ) : (
        <>
          <Card mode="contained">
            <Card.Content style={{ gap: 12 }}>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                <Chip>
                  {kitchen.status === "pending"
                    ? "Pending approval"
                    : kitchen.status === "approved"
                      ? "Approved"
                      : kitchen.status}
                </Chip>
                {kitchen.status === "approved" && (
                  <Chip>{kitchen.is_accepting_orders ? "Accepting orders" : "Orders paused"}</Chip>
                )}
              </View>
              <Text variant="bodyMedium">{kitchen.community_name}</Text>
              {kitchen.status === "pending" && (
                <Text variant="bodyMedium">
                  Your kitchen is awaiting platform approval. Set up items and save menu drafts
                  while it is reviewed. You can publish after approval.
                </Text>
              )}
              {suspended && (
                <HelperText type="error" visible>
                  Your kitchen is suspended. Contact the platform admin before changing kitchen
                  details or menus. You can still cancel listings without live orders.
                </HelperText>
              )}
              {kitchen.pause_reason && <Text variant="bodyMedium">{kitchen.pause_reason}</Text>}
              <Button
                mode="outlined"
                disabled={busy}
                loading={busy}
                onPress={() =>
                  run(async () => {
                    await refresh();
                    await reload();
                    return "Kitchen status refreshed.";
                  })
                }
              >
                {kitchen.status === "pending" ? "Check approval" : "Refresh kitchen"}
              </Button>
            </Card.Content>
          </Card>
          <SegmentedButtons
            value={section}
            onValueChange={(value) => {
              setSection(value);
              setError(null);
              setSuccess(null);
            }}
            buttons={[
              { value: "kitchen", label: "Kitchen", disabled: busy },
              { value: "items", label: "Items", disabled: busy },
              { value: "menus", label: "Menus", disabled: busy },
            ]}
          />
          {section === "kitchen" && (
            <>
              {editingKitchen ? (
                <Card mode="outlined">
                  <Card.Content>
                    <KitchenEditor
                      kitchen={kitchen}
                      busy={busy}
                      onSave={saveKitchen}
                      onCancel={() => setEditingKitchen(false)}
                      serverError={error}
                    />
                  </Card.Content>
                </Card>
              ) : (
                <Card mode="outlined">
                  <Card.Content style={{ gap: 12 }}>
                    <Text variant="titleMedium">Kitchen details</Text>
                    {kitchen.description && <Text variant="bodyMedium">{kitchen.description}</Text>}
                    <Text variant="bodyMedium">
                      {kitchen.address_label || "No kitchen address added yet."}
                    </Text>
                    {kitchen.zone_name && <Text variant="bodyMedium">{kitchen.zone_name}</Text>}
                    <Text variant="bodyMedium">
                      {[
                        kitchen.pickup_enabled && "Pickup",
                        kitchen.delivery_enabled &&
                          `Delivery (₹${(kitchen.delivery_fee_paise / 100).toFixed(2)})`,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </Text>
                    <Text variant="bodyMedium">
                      FSSAI: {kitchen.fssai_number || "Add your registration number for approval."}
                    </Text>
                    {kitchen.upi_id && <Text variant="bodyMedium">UPI: {kitchen.upi_id}</Text>}
                    <Button
                      mode="outlined"
                      disabled={busy || suspended}
                      onPress={() => setEditingKitchen(true)}
                    >
                      Edit kitchen
                    </Button>
                    {kitchen.status === "approved" && (
                      <Button
                        disabled={busy}
                        onPress={() =>
                          run(async () => {
                            await api(
                              `/api/v1/kitchens/${kitchen.id}/${kitchen.is_accepting_orders ? "pause" : "resume"}`,
                              {
                                method: "POST",
                                ...(kitchen.is_accepting_orders ? { body: {} } : {}),
                              },
                            );
                            assertCurrent();
                            await refresh();
                            return kitchen.is_accepting_orders
                              ? "New orders paused."
                              : "Kitchen is accepting new orders.";
                          })
                        }
                      >
                        {kitchen.is_accepting_orders ? "Pause new orders" : "Resume new orders"}
                      </Button>
                    )}
                  </Card.Content>
                </Card>
              )}
              <Text variant="titleLarge">Pickup points</Text>
              {points.isPending && <ActivityIndicator accessibilityLabel="Loading pickup points" />}
              <QueryFailure
                error={points.error}
                loading={points.isFetching}
                retry={() => void points.refetch()}
              />
              {sharedPoints.isPending && (
                <ActivityIndicator accessibilityLabel="Loading community pickup points" />
              )}
              {sharedPoints.error && (
                <Text variant="bodyMedium">Community pickup points could not be loaded.</Text>
              )}
              <QueryFailure
                error={sharedPoints.error}
                loading={sharedPoints.isFetching}
                retry={() => void sharedPoints.refetch()}
              />
              {!points.isPending &&
                !sharedPoints.isPending &&
                !points.error &&
                !pickupPoints.length && (
                  <Text variant="bodyMedium">
                    Add a pickup point with a real address before offering meals for pickup.
                  </Text>
                )}
              {pickupPoints.map((point) => (
                <Card key={point.id} mode="outlined">
                  <Card.Content style={{ gap: 8 }}>
                    <Text variant="titleMedium">
                      {point.name}
                      {point.active ? "" : " (inactive)"}
                    </Text>
                    {!point.kitchen_id && (
                      <Text variant="labelMedium">Shared community pickup point</Text>
                    )}
                    <Text variant="bodyMedium">{point.address_label}</Text>
                    {point.instructions && <Text variant="bodySmall">{point.instructions}</Text>}
                    {point.kitchen_id === kitchen.id && (
                      <Button disabled={busy || suspended} onPress={() => setEditingPoint(point)}>
                        Edit pickup point
                      </Button>
                    )}
                    {point.kitchen_id === kitchen.id && (
                      <Button
                        disabled={busy || suspended}
                        onPress={() =>
                          run(async () => {
                            await api(`/api/v1/kitchens/${kitchen.id}/pickup-points/${point.id}`, {
                              method: "PATCH",
                              body: { active: !point.active },
                            });
                            await reload();
                            return point.active
                              ? "Pickup point deactivated."
                              : "Pickup point activated.";
                          })
                        }
                      >
                        {point.active ? "Deactivate" : "Activate"}
                      </Button>
                    )}
                  </Card.Content>
                </Card>
              ))}
              <Button
                mode="outlined"
                disabled={busy || suspended}
                onPress={() => setEditingPoint(null)}
              >
                Add pickup point
              </Button>
              {editingPoint !== undefined && (
                <Card mode="outlined">
                  <Card.Content>
                    <PickupEditor
                      key={editingPoint?.id ?? "new"}
                      kitchen={kitchen}
                      point={editingPoint ?? undefined}
                      busy={busy}
                      onSave={savePoint}
                      onCancel={() => setEditingPoint(undefined)}
                      serverError={error}
                    />
                  </Card.Content>
                </Card>
              )}
            </>
          )}
          {section === "items" && (
            <>
              <Button
                mode="contained"
                disabled={busy || suspended}
                onPress={() => setEditingDish(null)}
              >
                New item
              </Button>
              {editingDish !== undefined && (
                <Card mode="outlined">
                  <Card.Content>
                    <DishEditor
                      key={editingDish?.id ?? "new"}
                      dish={editingDish ?? undefined}
                      busy={busy}
                      onSave={saveDish}
                      onCancel={() => setEditingDish(undefined)}
                      serverError={error}
                    />
                  </Card.Content>
                </Card>
              )}
              {dishes.isPending && <ActivityIndicator accessibilityLabel="Loading items" />}
              <QueryFailure
                error={dishes.error}
                loading={dishes.isFetching}
                retry={() => void dishes.refetch()}
              />
              {!dishes.isPending && !dishes.error && !items.length && (
                <Text variant="bodyMedium">
                  Create your first food item, then add it to a dated menu.
                </Text>
              )}
              {items.map((dish) => (
                <Card key={dish.id} mode="outlined">
                  {dish.image_url && <Card.Cover source={{ uri: dish.image_url }} />}
                  <Card.Content style={{ gap: 10, paddingTop: 16 }}>
                    <Text variant="titleMedium">{dish.name}</Text>
                    {dish.description && <Text variant="bodyMedium">{dish.description}</Text>}
                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                      <Button disabled={busy || suspended} onPress={() => setEditingDish(dish)}>
                        Edit item
                      </Button>
                      <Button
                        disabled={busy || suspended}
                        onPress={() => {
                          setError(null);
                          setArchiveDish(dish);
                        }}
                      >
                        Archive
                      </Button>
                    </View>
                  </Card.Content>
                </Card>
              ))}
              {dishes.hasNextPage && (
                <Button
                  disabled={dishes.isFetchingNextPage}
                  loading={dishes.isFetchingNextPage}
                  onPress={() => void dishes.fetchNextPage()}
                >
                  Load more items
                </Button>
              )}
            </>
          )}
          {section === "menus" && (
            <>
              <TextInput
                mode="outlined"
                label="Menu date (YYYY-MM-DD)"
                maxLength={10}
                value={date}
                disabled={busy}
                onChangeText={(value) => {
                  setDate(value);
                  setEditingListing(undefined);
                }}
              />
              {!validDate(date) && (
                <HelperText type="error" visible>
                  Enter a valid date in YYYY-MM-DD format.
                </HelperText>
              )}
              <Button
                mode="contained"
                disabled={
                  busy || suspended || !items.length || !validDate(date) || points.isPending
                }
                onPress={() => setEditingListing(null)}
              >
                Add menu item
              </Button>
              <QueryFailure
                error={dishes.error}
                loading={dishes.isFetching}
                retry={() => void dishes.refetch()}
              />
              {!items.length && !dishes.isPending && !dishes.error && (
                <Button
                  disabled={busy}
                  onPress={() => {
                    setSection("items");
                    setEditingDish(null);
                  }}
                >
                  Create an item first
                </Button>
              )}
              <QueryFailure
                error={points.error}
                loading={points.isFetching}
                retry={() => void points.refetch()}
              />
              {editingListing !== undefined && (
                <Card mode="outlined">
                  <Card.Content>
                    <ListingEditor
                      key={editingListing?.id ?? "new"}
                      kitchen={kitchen}
                      listing={editingListing ?? undefined}
                      dishes={items}
                      points={pickupPoints}
                      date={date}
                      busy={busy}
                      moreDishes={!!dishes.hasNextPage}
                      loadingDishes={dishes.isFetchingNextPage}
                      onMoreDishes={() => void dishes.fetchNextPage()}
                      onSave={saveListing}
                      onCancel={() => setEditingListing(undefined)}
                      onAddPickup={() => setEditingPoint(null)}
                      serverError={error}
                      sharedPointsError={sharedPoints.error ? failure(sharedPoints.error) : null}
                      loadingSharedPoints={sharedPoints.isFetching}
                      onRetrySharedPoints={() => void sharedPoints.refetch()}
                    />
                  </Card.Content>
                </Card>
              )}
              {editingPoint !== undefined && (
                <Card mode="outlined">
                  <Card.Content>
                    <PickupEditor
                      key={editingPoint?.id ?? "new"}
                      kitchen={kitchen}
                      point={editingPoint ?? undefined}
                      busy={busy}
                      onSave={savePoint}
                      onCancel={() => setEditingPoint(undefined)}
                      serverError={error}
                    />
                  </Card.Content>
                </Card>
              )}
              {menus.isPending && validDate(date) && (
                <ActivityIndicator accessibilityLabel="Loading daily menu" />
              )}
              <QueryFailure
                error={menus.error}
                loading={menus.isFetching}
                retry={() => void menus.refetch()}
              />
              {!menus.isPending && !menus.error && !listings.length && (
                <Text variant="bodyMedium">
                  No menu items for this day. Add an item and save a draft or publish when your
                  kitchen is approved.
                </Text>
              )}
              {listings.map((listing) => (
                <Card key={listing.id} mode="outlined">
                  <Card.Content style={{ gap: 10 }}>
                    <View style={{ alignItems: "flex-start" }}>
                      <Chip>{listing.status === "sold_out" ? "Sold out" : listing.status}</Chip>
                    </View>
                    <Text variant="titleMedium">{listing.dish.name}</Text>
                    <Text variant="bodyMedium">
                      ₹{(listing.price_paise / 100).toFixed(2)} · {listing.quantity_remaining} of{" "}
                      {listing.quantity_total} portions available
                    </Text>
                    <Text variant="bodySmall">
                      Ready {indiaTime(new Date(listing.available_from))}–
                      {indiaTime(new Date(listing.available_until))} · Orders close{" "}
                      {indiaTime(new Date(listing.order_cutoff))} IST
                    </Text>
                    <Text variant="bodySmall">
                      {[listing.pickup_enabled && "Pickup", listing.delivery_enabled && "Delivery"]
                        .filter(Boolean)
                        .join(" · ")}
                    </Text>
                    {listing.status !== "cancelled" && (
                      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                        <Button
                          disabled={busy || suspended}
                          onPress={() => setEditingListing(listing)}
                        >
                          Edit menu item
                        </Button>
                        {listing.status === "draft" && (
                          <Button
                            disabled={busy || kitchen.status !== "approved"}
                            onPress={() =>
                              run(async () => {
                                await api(`/api/v1/menu-listings/${listing.id}`, {
                                  method: "PATCH",
                                  body: { status: "published" },
                                });
                                await reload();
                                return "Menu item published.";
                              })
                            }
                          >
                            Publish
                          </Button>
                        )}
                        <Button
                          disabled={busy}
                          onPress={() => {
                            setError(null);
                            setCancelListing(listing);
                          }}
                        >
                          Cancel listing
                        </Button>
                      </View>
                    )}
                  </Card.Content>
                </Card>
              ))}
              {menus.hasNextPage && (
                <Button
                  disabled={menus.isFetchingNextPage}
                  loading={menus.isFetchingNextPage}
                  onPress={() => void menus.fetchNextPage()}
                >
                  Load more menu items
                </Button>
              )}
            </>
          )}
        </>
      )}
      <Portal>
        <Dialog
          visible={!!archiveDish}
          onDismiss={() => {
            if (!busy) setArchiveDish(null);
          }}
        >
          <Dialog.Title>Archive this item?</Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              {archiveDish?.name} will leave your reusable items. Existing order details remain
              available.
            </Text>
            {error && (
              <HelperText type="error" visible accessibilityLiveRegion="polite">
                {error}
              </HelperText>
            )}
          </Dialog.Content>
          <Dialog.Actions>
            <Button disabled={busy} onPress={() => setArchiveDish(null)}>
              Keep item
            </Button>
            <Button
              disabled={busy}
              loading={busy}
              onPress={() => {
                const dish = archiveDish;
                if (!dish) return;
                run(async () => {
                  await api(`/api/v1/dishes/${dish.id}`, { method: "DELETE" });
                  await reload();
                  if (mounted.current) {
                    setArchiveDish(null);
                    if (editingDish?.id === dish.id) setEditingDish(undefined);
                  }
                  return "Item archived.";
                });
              }}
            >
              Archive
            </Button>
          </Dialog.Actions>
        </Dialog>
        <Dialog
          visible={!!cancelListing}
          onDismiss={() => {
            if (!busy) setCancelListing(null);
          }}
        >
          <Dialog.Title>Cancel this listing?</Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              This stops new orders for {cancelListing?.dish.name} on this menu.
            </Text>
            {error && (
              <HelperText type="error" visible accessibilityLiveRegion="polite">
                {error}
              </HelperText>
            )}
          </Dialog.Content>
          <Dialog.Actions>
            <Button disabled={busy} onPress={() => setCancelListing(null)}>
              Keep listing
            </Button>
            <Button
              disabled={busy}
              loading={busy}
              onPress={() => {
                const listing = cancelListing;
                if (!listing) return;
                run(async () => {
                  await api(`/api/v1/menu-listings/${listing.id}`, {
                    method: "PATCH",
                    body: { status: "cancelled" },
                  });
                  await reload();
                  if (mounted.current) {
                    setCancelListing(null);
                    setEditingListing(undefined);
                  }
                  return "Listing cancelled.";
                });
              }}
            >
              Cancel listing
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </Screen>
  );
}
