"use client";
import Link from "next/link";
import { RelatedOrders, RelatedSection, RecordLink } from "@/components/organisms/related-records";
import { useState } from "react";
import {
  useAdminFoodKitchen,
  useAdminFoodKitchenMembers,
  useAdminFoodKitchenDishes,
  useAdminFoodKitchenListings,
  useAdminKitchenPrepSummary,
  adminFoodSuspendKitchen,
  adminFoodResumeKitchen,
  adminFoodUpdateKitchenMember,
  adminFoodDeleteKitchenMember,
  adminFoodArchiveDish,
  adminFoodRestoreDish,
  adminFoodCancelListing,
} from "@/lib/api/generated/admin";
import { today, money, dateTime } from "@/lib/utils";
import { PageHeading } from "@/components/molecules/page-heading";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { ActionButton } from "@/components/molecules/action-button";
import { Input } from "@/components/atoms/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/atoms/card";
import { DataTable } from "@/components/organisms/data-table";
import { FormLink } from "@/components/molecules/form-link";

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
            <FormLink href={`/kitchens/${id}/edit`}>Edit</FormLink>
            {kitchen.status !== "approved" && (
              <FormLink href={`/kitchens/${id}/approve`}>Approve kitchen</FormLink>
            )}
            {kitchen.status !== "suspended" && (
              <ActionButton
                label="Suspend kitchen"
                description="Remove this kitchen from discovery and block new orders."
                action={() => adminFoodSuspendKitchen(id)}
              />
            )}
            {kitchen.is_accepting_orders ? (
              <FormLink href={`/kitchens/${id}/pause`}>Pause orders</FormLink>
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
          <FormLink href={`/kitchens/${id}/listings/new?date=${encodeURIComponent(date)}`}>
            Publish listing
          </FormLink>
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
          <CardTitle className="text-base">
            Reusable dishes{dishes.data && ` (${dishes.data.total})`}
          </CardTitle>
          <FormLink href={`/kitchens/${id}/dishes/new`}>New dish</FormLink>
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
                        {row.is_active && (
                          <FormLink
                            href={`/kitchens/${id}/listings/new?dish_id=${row.id}&date=${encodeURIComponent(date)}`}
                          >
                            Cook again
                          </FormLink>
                        )}
                        <FormLink href={`/kitchens/${id}/dishes/${row.id}/edit`}>Edit</FormLink>
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
          <CardTitle className="text-base">
            Kitchen operators{members.data && ` (${members.data.total})`}
          </CardTitle>
          <FormLink href={`/kitchens/${id}/operators/new`}>Add operator</FormLink>
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
                    render: (row) => (
                      <RecordLink href={`/users/${row.user_id}`}>
                        {row.user_name ?? "Unnamed user"}
                      </RecordLink>
                    ),
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
      <RelatedSection title="Community" total={1}>
        <DataTable
          rows={[kitchen]}
          rowKey={(row) => row.community_id}
          columns={[
            {
              key: "community",
              title: "Community",
              render: (row) => (
                <RecordLink href={`/communities/${row.community_id}`}>
                  {row.community_name}
                </RecordLink>
              ),
            },
          ]}
        />
      </RelatedSection>
      <RelatedOrders filter={{ kitchen_id: id }} />
    </>
  );
}
