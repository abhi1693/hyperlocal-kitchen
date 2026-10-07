"use client";
import Link from "next/link";
import { useState } from "react";
import { useAdminFoodKitchens, adminFoodCreateKitchen } from "@/lib/api/generated/admin";
import type { AdminFoodKitchensStatus } from "@/lib/api/generated/models";
import { CommunityFilter } from "@/components/molecules/community-filter";
import { useListControls } from "@/lib/use-list-controls";
import { money } from "@/lib/utils";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { PageHeading } from "@/components/molecules/page-heading";
import { ListToolbar } from "@/components/molecules/list-toolbar";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { Textarea } from "@/components/atoms/textarea";
import { Select } from "@/components/atoms/select";
import { DataTable } from "@/components/organisms/data-table";
import { FormDialog } from "@/components/organisms/form-dialog";
export function KitchensPage({
  initialStatus = "",
}: {
  initialStatus?: NonNullable<AdminFoodKitchensStatus> | "";
}) {
  const controls = useListControls();
  const [status, setStatus] = useState(initialStatus);
  const [community, setCommunity] = useState("");
  const [filterCommunity, setFilterCommunity] = useState("");
  const query = useAdminFoodKitchens({
    ...controls.params,
    status: status || undefined,
    community_id: filterCommunity || undefined,
    sort: "name",
  });
  return (
    <>
      <PageHeading
        title="Kitchens"
        description="Review kitchens and manage their operators and menus."
        action={
          <FormDialog
            title="New kitchen"
            submit={(data) =>
              adminFoodCreateKitchen({
                name: String(data.get("name")),
                description: String(data.get("description") ?? "") || null,
                community_id: String(data.get("community_id")),
                owner_user_id: String(data.get("owner_user_id")),
                zone_id: String(data.get("zone_id") ?? "") || null,
                address_label: String(data.get("address_label") ?? "") || null,
                pickup_enabled: data.has("pickup_enabled"),
                delivery_enabled: data.has("delivery_enabled"),
                delivery_fee_paise: Math.round(Number(data.get("delivery_fee") ?? 0) * 100),
                upi_id: String(data.get("upi_id") ?? "") || null,
              })
            }
          >
            <Field label="Kitchen name" id="kitchen_name">
              <Input id="kitchen_name" name="name" required maxLength={150} />
            </Field>
            <Field label="Description" id="description">
              <Textarea id="description" name="description" maxLength={1000} />
            </Field>
            <ReferencePicker
              kind="community"
              name="community_id"
              label="Community"
              value={community}
              onChange={setCommunity}
            />
            <ReferencePicker
              key={community + "owner"}
              kind="user"
              name="owner_user_id"
              label="Owner"
              communityId={community}
            />
            <ReferencePicker
              key={community + "zone"}
              kind="zone"
              name="zone_id"
              label="Kitchen zone"
              communityId={community}
              required={false}
            />
            <Field
              label="Kitchen address"
              id="kitchen_address"
              hint="Independent of the owner’s home address. A pickup point is created when an address is provided."
            >
              <Input id="kitchen_address" name="address_label" maxLength={250} />
            </Field>
            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm">
                <Input type="checkbox" name="pickup_enabled" defaultChecked />
                Pickup
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Input type="checkbox" name="delivery_enabled" />
                Delivery
              </label>
            </div>
            <Field label="Delivery fee (₹)" id="delivery_fee">
              <Input
                id="delivery_fee"
                name="delivery_fee"
                type="number"
                min="0"
                max="10000"
                step="0.01"
                defaultValue="0"
              />
            </Field>
            <Field label="UPI ID" id="upi_id">
              <Input id="upi_id" name="upi_id" maxLength={150} />
            </Field>
          </FormDialog>
        }
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <CommunityFilter
          value={filterCommunity}
          onChange={(value) => {
            setFilterCommunity(value);
            controls.setOffset(0);
          }}
        />
        <Select
          aria-label="Kitchen status"
          className="w-auto"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as NonNullable<AdminFoodKitchensStatus> | "");
            controls.setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          <option value="pending">Pending approval</option>
          <option value="approved">Approved</option>
          <option value="suspended">Suspended</option>
        </Select>
      </ListToolbar>
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
      {query.data && (
        <>
          <DataTable
            rows={query.data.items}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "name",
                title: "Kitchen",
                render: (row) => (
                  <Link href={`/kitchens/${row.id}`} className="font-medium hover:underline">
                    {row.name}
                  </Link>
                ),
              },
              {
                key: "community",
                title: "Community",
                render: (row) => row.community_name,
              },
              {
                key: "zone",
                title: "Zone",
                render: (row) => row.zone_name ?? "—",
              },
              {
                key: "status",
                title: "Approval",
                render: (row) => <StatusBadge value={row.status} />,
              },
              {
                key: "availability",
                title: "New orders",
                render: (row) => (
                  <StatusBadge value={row.is_accepting_orders ? "accepting" : "paused"} />
                ),
              },
              {
                key: "fulfillment",
                title: "Fulfillment",
                render: (row) =>
                  [
                    row.pickup_enabled ? "Pickup" : null,
                    row.delivery_enabled ? `Delivery ${money(row.delivery_fee_paise)}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · "),
              },
            ]}
          />
          <Pagination
            total={query.data.total}
            offset={controls.offset}
            onPage={controls.setOffset}
          />
        </>
      )}
    </>
  );
}
