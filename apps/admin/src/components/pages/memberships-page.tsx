"use client";
import { useState } from "react";
import {
  useAdminListMemberships,
  useAdminGetUser,
  adminActivateMembership,
  adminSuspendMembership,
} from "@/lib/api/generated/admin";
import type { AdminListMembershipsStatus } from "@/lib/api/generated/models";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { CommunityFilter } from "@/components/molecules/community-filter";
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
export function MembershipsPage({
  initialCommunity = "",
  initialUser = "",
}: {
  initialCommunity?: string;
  initialUser?: string;
}) {
  const controls = useListControls();
  const [community, setCommunity] = useState(initialCommunity);
  const [userId, setUserId] = useState(initialUser);
  const selectedUser = useAdminGetUser(userId, { query: { enabled: !!userId } });
  const [status, setStatus] = useState<NonNullable<AdminListMembershipsStatus> | "">("");
  const query = useAdminListMemberships({
    ...controls.params,
    community_id: community || undefined,
    user_id: userId || undefined,
    status: status || undefined,
  });
  return (
    <>
      <PageHeading
        title="Memberships"
        description="An account can belong to several communities."
        action={<FormLink href={"/memberships/new"}>Add membership</FormLink>}
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <CommunityFilter
          value={community}
          onChange={(value) => {
            setCommunity(value);
            controls.setOffset(0);
          }}
        />
        <ReferencePicker
          kind="user"
          name="membership_user_filter"
          label="User filter"
          inline
          required={false}
          emptyLabel="All users"
          value={userId}
          selectedLabel={selectedUser.data?.name ?? selectedUser.data?.phone ?? undefined}
          onChange={(next) => {
            setUserId(next);
            controls.setOffset(0);
          }}
        />
        <Combobox
          label="Membership status"
          aria-label="Membership status"
          className="w-auto"
          value={status}
          onValueChange={(value) => {
            setStatus(value as NonNullable<AdminListMembershipsStatus> | "");
            controls.setOffset(0);
          }}
          options={[
            { value: "", label: "All statuses" },
            { value: "active", label: "Active" },
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
                key: "user",
                title: "Resident",
                render: (row) => row.user_name ?? row.phone ?? "Unnamed resident",
              },
              {
                key: "community",
                title: "Community",
                render: (row) => row.community_name,
              },
              {
                key: "home",
                title: "Home",
                render: (row) =>
                  [row.zone_name, row.address_label].filter(Boolean).join(" · ") || "—",
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
                  <ActionButton
                    label={row.status === "active" ? "Suspend" : "Activate"}
                    description="Change this resident’s access to this community."
                    action={() =>
                      row.status === "active"
                        ? adminSuspendMembership(row.id)
                        : adminActivateMembership(row.id)
                    }
                  />
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
