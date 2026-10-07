"use client";
import Link from "next/link";
import { useState } from "react";
import {
  useAdminListCommunities,
  adminCreateCommunity,
  adminUpdateCommunity,
  adminActivateCommunity,
  adminPauseCommunity,
} from "@/lib/api/generated/admin";
import {
  CommunityCreateType,
  type CommunityOut,
  type AdminListCommunitiesStatus,
} from "@/lib/api/generated/models";
import { useListControls } from "@/lib/use-list-controls";
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
function CommunityForm({ row }: { row?: CommunityOut }) {
  return (
    <FormDialog
      title={row ? "Edit community" : "New community"}
      label={row ? "Edit" : "New community"}
      submit={(data) => {
        const payload = {
          name: String(data.get("name")),
          city: String(data.get("city")),
          type: String(data.get("type")) as CommunityCreateType,
          address: String(data.get("address") ?? "") || null,
          postal_code: String(data.get("postal_code") ?? "") || null,
        };
        return row ? adminUpdateCommunity(row.id, payload) : adminCreateCommunity(payload);
      }}
    >
      <Field id="name" label="Name">
        <Input id="name" name="name" required maxLength={200} defaultValue={row?.name} />
      </Field>
      <Field id="type" label="Community type">
        <Select id="type" name="type" defaultValue={row?.type ?? "residential_society"}>
          {Object.values(CommunityCreateType).map((value) => (
            <option key={value} value={value}>
              {value.replaceAll("_", " ")}
            </option>
          ))}
        </Select>
      </Field>
      <Field id="city" label="City">
        <Input id="city" name="city" required maxLength={100} defaultValue={row?.city} />
      </Field>
      <Field id="address" label="Address">
        <Input id="address" name="address" maxLength={500} defaultValue={row?.address ?? ""} />
      </Field>
      <Field id="postal_code" label="Postal code">
        <Input
          id="postal_code"
          name="postal_code"
          maxLength={20}
          defaultValue={row?.postal_code ?? ""}
        />
      </Field>
    </FormDialog>
  );
}
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
        action={<CommunityForm />}
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <Select
          aria-label="Community status"
          className="w-auto"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as NonNullable<AdminListCommunitiesStatus> | "");
            controls.setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="paused">Paused</option>
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
                render: (row) => row.type.replaceAll("_", " "),
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
                    <CommunityForm row={row} />
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
