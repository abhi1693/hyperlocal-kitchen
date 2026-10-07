"use client";
import Link from "next/link";
import { useState } from "react";
import {
  useAdminListCommunities,
  adminActivateCommunity,
  adminPauseCommunity,
} from "@/lib/api/generated/admin";
import { type AdminListCommunitiesStatus } from "@/lib/api/generated/models";
import { communityTypeLabels } from "@/lib/api/community-type-choices";
import { useListControls } from "@/lib/use-list-controls";
import { PageHeading } from "@/components/molecules/page-heading";
import { ListToolbar } from "@/components/molecules/list-toolbar";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { ActionButton } from "@/components/molecules/action-button";
import { Combobox } from "@/components/molecules/combobox";
import { DataTable } from "@/components/organisms/data-table";
import { FormLink } from "@/components/molecules/form-link";
export function CommunitiesPage() {
  const controls = useListControls();
  const [status, setStatus] = useState<NonNullable<AdminListCommunitiesStatus> | "">("");
  const query = useAdminListCommunities({
    ...controls.params,
    status: status || undefined,
    sort: "name",
  });
  return (
    <>
      <PageHeading
        title="Communities"
        description="Manage communities and their service locations."
        action={<FormLink href={"/communities/new"}>New community</FormLink>}
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <Combobox
          label="Community status"
          aria-label="Community status"
          className="w-auto"
          value={status}
          onValueChange={(value) => {
            setStatus(value as NonNullable<AdminListCommunitiesStatus> | "");
            controls.setOffset(0);
          }}
          options={[
            { value: "", label: "All statuses" },
            { value: "draft", label: "Draft" },
            { value: "active", label: "Active" },
            { value: "paused", label: "Paused" },
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
                title: "Community",
                render: (row) => (
                  <Link className="font-medium hover:underline" href={`/communities/${row.id}`}>
                    {row.name}
                  </Link>
                ),
              },
              { key: "city", title: "City", render: (row) => row.city },
              {
                key: "type",
                title: "Type",
                render: (row) => communityTypeLabels[row.type],
              },
              {
                key: "status",
                title: "Status",
                render: (row) => <StatusBadge value={row.status} />,
              },
              {
                key: "actions",
                title: "Actions",
                render: (row) => (
                  <div className="flex gap-2">
                    <FormLink href={`/communities/${row.id}/edit`}>Edit</FormLink>
                    <ActionButton
                      label={row.status === "active" ? "Pause" : "Activate"}
                      description={
                        row.status === "active"
                          ? "Pause discovery and new activity in this community. Existing orders are retained."
                          : "Allow members to discover kitchens and place orders in this community."
                      }
                      action={() =>
                        row.status === "active"
                          ? adminPauseCommunity(row.id)
                          : adminActivateCommunity(row.id)
                      }
                    />
                  </div>
                ),
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
