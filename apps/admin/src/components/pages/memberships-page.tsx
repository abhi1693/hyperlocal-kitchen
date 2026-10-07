"use client";
import { useState } from "react";
import {
  useAdminListMemberships,
  adminCreateMembership,
  adminActivateMembership,
  adminSuspendMembership,
} from "@/lib/api/generated/admin";
import type { AdminListMembershipsStatus } from "@/lib/api/generated/models";
import { CommunityFilter } from "@/components/molecules/community-filter";
import { useListControls } from "@/lib/use-list-controls";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { PageHeading } from "@/components/molecules/page-heading";
import { ListToolbar } from "@/components/molecules/list-toolbar";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { ActionButton } from "@/components/molecules/action-button";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { Select } from "@/components/atoms/select";
import { DataTable } from "@/components/organisms/data-table";
import { FormDialog } from "@/components/organisms/form-dialog";
export function MembershipsPage({ initialCommunity = "" }: { initialCommunity?: string }) {
  const controls = useListControls();
  const [community, setCommunity] = useState(initialCommunity);
  const [formCommunity, setFormCommunity] = useState("");
  const [status, setStatus] = useState<NonNullable<AdminListMembershipsStatus> | "">("");
  const query = useAdminListMemberships({
    ...controls.params,
    community_id: community || undefined,
    status: status || undefined,
  });
  return (
    <>
      <PageHeading
        title="Memberships"
        description="An account can belong to several communities."
        action={
          <FormDialog
            title="Add membership"
            submit={(data) =>
              adminCreateMembership({
                user_id: String(data.get("user_id")),
                community_id: String(data.get("community_id")),
                zone_id: String(data.get("zone_id") ?? "") || null,
                address_label: String(data.get("address_label") ?? "") || null,
              })
            }
          >
            <ReferencePicker kind="user" name="user_id" label="User" />
            <ReferencePicker
              kind="community"
              name="community_id"
              label="Community"
              value={formCommunity}
              onChange={setFormCommunity}
            />
            <ReferencePicker
              key={formCommunity}
              kind="zone"
              name="zone_id"
              label="Home zone"
              communityId={formCommunity}
              required={false}
            />
            <Field label="Home address" id="home_address">
              <Input id="home_address" name="address_label" maxLength={250} />
            </Field>
          </FormDialog>
        }
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <CommunityFilter
          value={community}
          onChange={(value) => {
            setCommunity(value);
            controls.setOffset(0);
          }}
        />
        <Select
          aria-label="Membership status"
          className="w-auto"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as NonNullable<AdminListMembershipsStatus> | "");
            controls.setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
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
