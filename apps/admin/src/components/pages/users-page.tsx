"use client";
import { useState } from "react";
import {
  useAdminListUsers,
  adminUpdateUser,
  adminActivateUser,
  adminDeactivateUser,
} from "@/lib/api/generated/admin";
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
export function UsersPage() {
  const controls = useListControls();
  const [active, setActive] = useState("");
  const query = useAdminListUsers({
    ...controls.params,
    is_active: active ? active === "active" : undefined,
    sort: "name",
  });
  return (
    <>
      <PageHeading
        title="Users"
        description="Manage existing accounts. New users join through sign-in."
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <Select
          aria-label="Account status"
          className="w-auto"
          value={active}
          onChange={(event) => {
            setActive(event.target.value);
            controls.setOffset(0);
          }}
        >
          <option value="">All accounts</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
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
                title: "Name",
                render: (row) => row.name ?? "Unnamed user",
              },
              {
                key: "phone",
                title: "Phone",
                render: (row) => row.phone ?? "—",
              },
              {
                key: "active",
                title: "Status",
                render: (row) => <StatusBadge value={row.is_active ? "active" : "inactive"} />,
              },
              {
                key: "actions",
                title: "Actions",
                render: (row) => (
                  <div className="flex gap-2">
                    <FormDialog
                      title="Edit user"
                      label="Edit"
                      submit={(data) =>
                        adminUpdateUser(row.id, {
                          name: String(data.get("name")) || null,
                        })
                      }
                    >
                      <Field label="Name" id="user_name">
                        <Input
                          id="user_name"
                          name="name"
                          maxLength={120}
                          defaultValue={row.name ?? ""}
                        />
                      </Field>
                    </FormDialog>
                    <ActionButton
                      label={row.is_active ? "Deactivate" : "Activate"}
                      description={
                        row.is_active
                          ? "Disable this account and its memberships. A kitchen that loses its last active owner will be suspended."
                          : "Reactivate this account. Community memberships must be restored separately."
                      }
                      action={() =>
                        row.is_active ? adminDeactivateUser(row.id) : adminActivateUser(row.id)
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
