"use client";
import Link from "next/link";
import { useState } from "react";
import {
  useAdminFoodKitchen,
  useAdminFoodKitchenMembers,
  useAdminFoodKitchenDishes,
  useAdminFoodKitchenListings,
  useAdminKitchenPrepSummary,
  adminFoodApproveKitchen,
  adminFoodSuspendKitchen,
  adminFoodPauseKitchen,
  adminFoodResumeKitchen,
  adminFoodUpdateKitchen,
  adminFoodCreateKitchenMember,
  adminFoodUpdateKitchenMember,
  adminFoodDeleteKitchenMember,
  adminFoodCreateKitchenDish,
  adminFoodUpdateDish,
  adminFoodArchiveDish,
  adminFoodRestoreDish,
  adminFoodCancelListing,
} from "@/lib/api/generated/admin";
import type { DishOut, KitchenMemberCreateRole } from "@/lib/api/generated/models";
import { today, money, dateTime } from "@/lib/utils";
import { PageHeading } from "@/components/molecules/page-heading";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { ActionButton } from "@/components/molecules/action-button";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { Textarea } from "@/components/atoms/textarea";
import { Select } from "@/components/atoms/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/atoms/card";
import { DataTable } from "@/components/organisms/data-table";
import { FormDialog } from "@/components/organisms/form-dialog";
import { ListingForm } from "@/components/organisms/listing-form";
export function KitchenDetailPage({ id }: { id: string }) {
  const [date, setDate] = useState(today);
  const [memberOffset, setMemberOffset] = useState(0);
  const [dishOffset, setDishOffset] = useState(0);
  const [listingOffset, setListingOffset] = useState(0);
  const query = useAdminFoodKitchen(id);
  const members = useAdminFoodKitchenMembers(id, {
    limit: 30,
    offset: memberOffset,
  });
  const dishes = useAdminFoodKitchenDishes(id, {
    limit: 30,
    offset: dishOffset,
  });
  const listings = useAdminFoodKitchenListings(id, {
    service_date: date,
    limit: 30,
    offset: listingOffset,
  });
  const prep = useAdminKitchenPrepSummary(id, { date });
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const kitchen = query.data;
  function dishForm(row?: DishOut) {
    return (
      <FormDialog
        title={row ? "Edit dish" : "New dish"}
        label={row ? "Edit" : "New dish"}
        submit={(data) => {
          const payload = {
            name: String(data.get("name")),
            description: String(data.get("description") ?? "") || null,
            image_url: String(data.get("image_url") ?? "") || null,
          };
          return row
            ? adminFoodUpdateDish(row.id, payload)
            : adminFoodCreateKitchenDish(id, payload);
        }}
      >
        <Field label="Dish name" id="dish_name">
          <Input id="dish_name" name="name" required maxLength={150} defaultValue={row?.name} />
        </Field>
        <Field label="Description" id="dish_description">
          <Textarea
            id="dish_description"
            name="description"
            maxLength={1000}
            defaultValue={row?.description ?? ""}
          />
        </Field>
        <Field label="Photo URL" id="dish_photo">
          <Input
            id="dish_photo"
            name="image_url"
            type="url"
            placeholder="https://…"
            maxLength={2048}
            defaultValue={row?.image_url ?? ""}
          />
        </Field>
      </FormDialog>
    );
  }
  return (
    <>
      <Link href="/kitchens" className="text-sm text-muted-foreground hover:underline">
        ← Kitchens
      </Link>
      <PageHeading
        title={kitchen.name}
        description={`${kitchen.community_name} · ${kitchen.description ?? "Manage kitchen operations."}`}
        action={
          <div className="flex gap-2">
            <StatusBadge value={kitchen.status} />
            <StatusBadge value={kitchen.is_accepting_orders ? "accepting orders" : "paused"} />
          </div>
        }
      />
      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex flex-wrap gap-2">
            <FormDialog
              title="Edit kitchen"
              label="Edit"
              submit={(data) =>
                adminFoodUpdateKitchen(id, {
                  name: String(data.get("name")),
                  description: String(data.get("description") ?? "") || null,
                  address_label: String(data.get("address_label") ?? "") || null,
                  upi_id: String(data.get("upi_id") ?? "") || null,
                  pickup_enabled: data.has("pickup_enabled"),
                  delivery_enabled: data.has("delivery_enabled"),
                  delivery_fee_paise: Math.round(Number(data.get("delivery_fee")) * 100),
                })
              }
            >
              <Field label="Name" id="edit_kitchen_name">
                <Input
                  id="edit_kitchen_name"
                  name="name"
                  required
                  maxLength={150}
                  defaultValue={kitchen.name}
                />
              </Field>
              <Field label="Description" id="edit_description">
                <Textarea
                  id="edit_description"
                  name="description"
                  maxLength={1000}
                  defaultValue={kitchen.description ?? ""}
                />
              </Field>
              <Field label="Kitchen address" id="edit_address">
                <Input
                  id="edit_address"
                  name="address_label"
                  maxLength={250}
                  defaultValue={kitchen.address_label ?? ""}
                />
              </Field>
              <Field label="UPI ID" id="edit_upi">
                <Input
                  id="edit_upi"
                  name="upi_id"
                  maxLength={150}
                  defaultValue={kitchen.upi_id ?? ""}
                />
              </Field>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <Input
                    type="checkbox"
                    name="pickup_enabled"
                    defaultChecked={kitchen.pickup_enabled}
                  />
                  Pickup
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <Input
                    type="checkbox"
                    name="delivery_enabled"
                    defaultChecked={kitchen.delivery_enabled}
                  />
                  Delivery
                </label>
              </div>
              <Field label="Delivery fee (₹)" id="edit_delivery_fee">
                <Input
                  id="edit_delivery_fee"
                  name="delivery_fee"
                  type="number"
                  min="0"
                  max="10000"
                  step="0.01"
                  defaultValue={kitchen.delivery_fee_paise / 100}
                />
              </Field>
            </FormDialog>
            {kitchen.status !== "approved" && (
              <FormDialog
                title="Approve kitchen"
                submit={(data) =>
                  adminFoodApproveKitchen(id, {
                    fssai_number: String(data.get("fssai_number")),
                  })
                }
              >
                <Field label="FSSAI number" id="fssai_number">
                  <Input
                    id="fssai_number"
                    name="fssai_number"
                    inputMode="numeric"
                    pattern="[0-9]{14}"
                    maxLength={14}
                    required
                    defaultValue={kitchen.fssai_number ?? ""}
                  />
                </Field>
              </FormDialog>
            )}
            {kitchen.status !== "suspended" && (
              <ActionButton
                label="Suspend kitchen"
                description="Remove this kitchen from discovery and block new orders."
                action={() => adminFoodSuspendKitchen(id)}
              />
            )}
            {kitchen.is_accepting_orders ? (
              <FormDialog
                title="Pause orders"
                description="Existing orders will not be affected."
                submit={(data) =>
                  adminFoodPauseKitchen(id, {
                    reason: String(data.get("reason") ?? "") || null,
                  })
                }
              >
                <Field label="Reason (optional)" id="pause_reason">
                  <Textarea id="pause_reason" name="reason" maxLength={500} />
                </Field>
              </FormDialog>
            ) : (
              <ActionButton
                label="Resume orders"
                description="Allow new orders again. Kitchen approval is still required."
                action={() => adminFoodResumeKitchen(id)}
              />
            )}
          </div>
          {kitchen.pause_reason && (
            <p className="text-sm text-muted-foreground">Pause reason: {kitchen.pause_reason}</p>
          )}
          <dl className="grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Kitchen address</dt>
              <dd>
                {[kitchen.zone_name, kitchen.address_label].filter(Boolean).join(" · ") || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">FSSAI number</dt>
              <dd>{kitchen.fssai_number ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">UPI</dt>
              <dd>{kitchen.upi_id ?? "—"}</dd>
            </div>
          </dl>
          <Link
            href={`/communities/${kitchen.community_id}`}
            className="inline-block text-sm underline"
          >
            Community and pickup points
          </Link>
        </CardContent>
      </Card>
      <div className="flex items-center gap-3">
        <label htmlFor="operation_date" className="text-sm font-medium">
          Service date
        </label>
        <Input
          id="operation_date"
          type="date"
          required
          value={date}
          className="w-auto"
          onChange={(event) => {
            if (event.target.value) {
              setDate(event.target.value);
              setListingOffset(0);
            }
          }}
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Preparation summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <QueryState pending={prep.isPending} error={prep.error} retry={() => prep.refetch()} />
          {prep.data && (
            <>
              <p className="text-sm text-muted-foreground">
                {prep.data.total_portions} portions across {prep.data.order_count} accepted,
                preparing or ready orders.
              </p>
              <DataTable
                rows={prep.data.items}
                rowKey={(row) => row.dish_id + row.dish_name}
                empty="No outstanding preparation for this date."
                columns={[
                  {
                    key: "dish",
                    title: "Dish",
                    render: (row) => row.dish_name,
                  },
                  {
                    key: "quantity",
                    title: "Portions",
                    render: (row) => row.portion_count,
                  },
                  {
                    key: "notes",
                    title: "Customer notes",
                    render: (row) =>
                      row.notes.length ? (
                        <ul className="space-y-1">
                          {row.notes.map((note) => (
                            <li key={note.order_id}>
                              <Link className="underline" href={`/orders/${note.order_id}`}>
                                #{note.order_number}
                              </Link>{" "}
                              · {note.quantity} portions · {note.customer_note}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        "—"
                      ),
                  },
                ]}
              />
            </>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Menu for {date}</CardTitle>
          <ListingForm kitchen={kitchen} />
        </CardHeader>
        <CardContent className="space-y-4">
          <QueryState
            pending={listings.isPending}
            error={listings.error}
            retry={() => listings.refetch()}
          />
          {listings.data && (
            <>
              <DataTable
                rows={listings.data.items}
                rowKey={(row) => row.id}
                columns={[
                  {
                    key: "dish",
                    title: "Dish",
                    render: (row) => row.dish.name,
                  },
                  {
                    key: "portions",
                    title: "Remaining",
                    render: (row) => `${row.quantity_remaining} / ${row.quantity_total}`,
                  },
                  {
                    key: "price",
                    title: "Price",
                    render: (row) => money(row.price_paise),
                  },
                  {
                    key: "cutoff",
                    title: "Orders close",
                    render: (row) => dateTime(row.order_cutoff),
                  },
                  {
                    key: "status",
                    title: "Status",
                    render: (row) => <StatusBadge value={row.status} />,
                  },
                  {
                    key: "actions",
                    title: "Actions",
                    render: (row) =>
                      row.status !== "cancelled" ? (
                        <ActionButton
                          label="Cancel listing"
                          action={() => adminFoodCancelListing(row.id)}
                          description="Stop new orders for this listing. Listings with reserved portions cannot be cancelled."
                        />
                      ) : (
                        "—"
                      ),
                  },
                ]}
              />
              <Pagination
                total={listings.data.total}
                offset={listingOffset}
                onPage={setListingOffset}
              />
            </>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Reusable dishes</CardTitle>
          {dishForm()}
        </CardHeader>
        <CardContent className="space-y-4">
          <QueryState
            pending={dishes.isPending}
            error={dishes.error}
            retry={() => dishes.refetch()}
          />
          {dishes.data && (
            <>
              <DataTable
                rows={dishes.data.items}
                rowKey={(row) => row.id}
                columns={[
                  { key: "name", title: "Dish", render: (row) => row.name },
                  {
                    key: "active",
                    title: "Status",
                    render: (row) => <StatusBadge value={row.is_active ? "active" : "archived"} />,
                  },
                  {
                    key: "actions",
                    title: "Actions",
                    render: (row) => (
                      <div className="flex flex-wrap gap-2">
                        {row.is_active && <ListingForm kitchen={kitchen} dish={row} />}
                        {dishForm(row)}
                        <ActionButton
                          label={row.is_active ? "Archive" : "Restore"}
                          action={() =>
                            row.is_active
                              ? adminFoodArchiveDish(row.id)
                              : adminFoodRestoreDish(row.id)
                          }
                        />
                      </div>
                    ),
                  },
                ]}
              />
              <Pagination total={dishes.data.total} offset={dishOffset} onPage={setDishOffset} />
            </>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Kitchen operators</CardTitle>
          <FormDialog
            title="Add operator"
            submit={(data) =>
              adminFoodCreateKitchenMember(id, {
                user_id: String(data.get("user_id")),
                role: String(data.get("role")) as KitchenMemberCreateRole,
              })
            }
          >
            <ReferencePicker
              kind="user"
              name="user_id"
              label="Resident"
              communityId={kitchen.community_id}
            />
            <Field label="Role" id="operator_role">
              <Select id="operator_role" name="role">
                <option value="manager">Manager</option>
                <option value="owner">Owner</option>
              </Select>
            </Field>
          </FormDialog>
        </CardHeader>
        <CardContent className="space-y-4">
          <QueryState
            pending={members.isPending}
            error={members.error}
            retry={() => members.refetch()}
          />
          {members.data && (
            <>
              <DataTable
                rows={members.data.items}
                rowKey={(row) => row.user_id}
                columns={[
                  {
                    key: "name",
                    title: "Operator",
                    render: (row) => row.user_name ?? "Unnamed user",
                  },
                  {
                    key: "role",
                    title: "Role",
                    render: (row) => <StatusBadge value={row.role} />,
                  },
                  {
                    key: "actions",
                    title: "Actions",
                    render: (row) => (
                      <div className="flex gap-2">
                        <ActionButton
                          label={row.role === "owner" ? "Make manager" : "Make owner"}
                          action={() =>
                            adminFoodUpdateKitchenMember(id, row.user_id, {
                              role: row.role === "owner" ? "manager" : "owner",
                            })
                          }
                        />
                        <ActionButton
                          label="Remove"
                          action={() => adminFoodDeleteKitchenMember(id, row.user_id)}
                          description="Remove this operator’s access. At least one active owner must remain."
                        />
                      </div>
                    ),
                  },
                ]}
              />
              <Pagination
                total={members.data.total}
                offset={memberOffset}
                onPage={setMemberOffset}
              />
            </>
          )}
        </CardContent>
      </Card>
    </>
  );
}
