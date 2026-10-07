"use client";
import Link from "next/link";
import { useState } from "react";
import { useAdminListUsers } from "@/lib/api/generated/admin";
import { useListControls } from "@/lib/use-list-controls";
import { PageHeading } from "@/components/molecules/page-heading";
import { ListToolbar } from "@/components/molecules/list-toolbar";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { QueryState } from "@/components/molecules/query-state";
import { Combobox } from "@/components/molecules/combobox";
import { DataTable } from "@/components/organisms/data-table";
import { FormLink } from "@/components/molecules/form-link";
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
        description="View profiles, edit contact details and manage account access."
      />
      <ListToolbar search={controls.search} onSearch={controls.onSearch}>
        <Combobox
          label="Account status"
          aria-label="Account status"
          className="w-auto"
          value={active}
          onValueChange={(value) => {
            setActive(value);
            controls.setOffset(0);
          }}
          options={[
            { value: "", label: "All accounts" },
            { value: "active", label: "Active" },
            { value: "inactive", label: "Inactive" },
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
                title: "Name",
                render: (row) => (
                  <Link href={`/users/${row.id}`} className="font-medium hover:underline">
                    {row.name ?? "Unnamed user"}
                  </Link>
                ),
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
                    <FormLink href={`/users/${row.id}/edit`}>Edit</FormLink>
                    <FormLink href={`/users/${row.id}/delete`}>Delete</FormLink>
                    <FormLink
                      href={`/users/${row.id}/${row.is_active ? "deactivate" : "activate"}`}
                    >
                      {row.is_active ? "Deactivate" : "Activate"}
                    </FormLink>
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
