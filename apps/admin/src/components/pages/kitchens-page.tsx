"use client";
import Link from "next/link";
import { useState } from "react";
import { useAdminFoodKitchens } from "@/lib/api/generated/admin";
import type { AdminFoodKitchensStatus } from "@/lib/api/generated/models";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { CommunityFilter } from "@/components/molecules/community-filter";
import { useListControls } from "@/lib/use-list-controls";
import { money } from "@/lib/utils";
import { PageHeading } from "@/components/molecules/page-heading";
import { ListToolbar } from "@/components/molecules/list-toolbar";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { Combobox } from "@/components/molecules/combobox";
import { DataTable } from "@/components/organisms/data-table";
import { FormLink } from "@/components/molecules/form-link";
export function KitchensPage({
  initialStatus = "",
  initialCommunity = "",
  userId,
}: {
  initialStatus?: NonNullable<AdminFoodKitchensStatus> | "";
  initialCommunity?: string;
  userId?: string;
}) {
  const controls = useListControls();
  const [operator, setOperator] = useState(userId ?? "");
  const [status, setStatus] = useState(initialStatus);
  const [filterCommunity, setFilterCommunity] = useState(initialCommunity);
  const query = useAdminFoodKitchens({
    ...controls.params,
    user_id: operator || undefined,
    status: status || undefined,
    community_id: filterCommunity || undefined,
    sort: "name",
  });
  return (
    <>
      <PageHeading
        title="Kitchens"
        description="Review kitchens and manage their operators and menus."
        action={<FormLink href={"/kitchens/new"}>New kitchen</FormLink>}
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <CommunityFilter
          value={filterCommunity}
          onChange={(value) => {
            setFilterCommunity(value);
            controls.setOffset(0);
          }}
        />
        <ReferencePicker
          kind="user"
          name="user_filter"
          required={false}
          emptyLabel="All users"
          label="Operator filter"
          inline
          value={operator}
          onChange={(value) => {
            setOperator(value);
            controls.setOffset(0);
          }}
        />
        <Combobox
          label="Kitchen status"
          aria-label="Kitchen status"
          className="w-auto"
          value={status}
          onValueChange={(value) => {
            setStatus(value as NonNullable<AdminFoodKitchensStatus> | "");
            controls.setOffset(0);
          }}
          options={[
            { value: "", label: "All statuses" },
            { value: "pending", label: "Pending approval" },
            { value: "approved", label: "Approved" },
            { value: "suspended", label: "Suspended" },
          ]}
        />
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
